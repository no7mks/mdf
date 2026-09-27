"""联调 inbox 与可选 HTTP。"""
from __future__ import annotations
import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from conftest import skill_dir
from mdf_test_support import assert_ok, git, init_git, mdf, payload


def _poll_proc(
    python_exe: str, repo: Path, *extra: str
) -> subprocess.Popen:
    cli = skill_dir("mdf") / "scripts" / "mdf.py"
    return subprocess.Popen(
        [
            python_exe, str(cli), "integrate", "poll",
            "--repo", str(repo), *extra,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _lines(proc: subprocess.Popen) -> queue.Queue:
    """逐行读 stdout；select 看不到已读进缓冲区的行，不能与 readline 混用。"""
    lines = getattr(proc, "mdf_lines", None)
    if lines is None:
        lines = queue.Queue()

        def pump() -> None:
            for line in proc.stdout:
                lines.put(line)
            lines.put("")

        proc.mdf_lines = lines
        proc.mdf_reader = threading.Thread(target=pump, daemon=True)
        proc.mdf_reader.start()
    return lines


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)
    reader = getattr(proc, "mdf_reader", None)
    if reader is not None:
        reader.join(timeout=5)
    if proc.stdout is not None:
        proc.stdout.close()
    if proc.stderr is not None:
        proc.stderr.close()


def _next_event(proc: subprocess.Popen, timeout: float = 5) -> dict:
    assert proc.stdout is not None
    try:
        line = _lines(proc).get(timeout=timeout)
    except queue.Empty:
        raise AssertionError("poll 没有输出") from None
    assert line, "poll stdout 关闭"
    return json.loads(line)


def _next_message(proc: subprocess.Popen, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        event = _next_event(proc, timeout=max(0.05, deadline - time.monotonic()))
        if event.get("event") == "message":
            return event["message"]
    raise AssertionError("poll 没有交出消息")


def _repo(path: Path, name: str) -> Path:
    repo = path / name
    repo.mkdir()
    (repo / "README.md").write_text(f"{name}\n", encoding="utf-8")
    init_git(repo)
    return repo


def test_local_send_keeps_poll_running(tmp_path: Path, python_exe: str) -> None:
    left = _repo(tmp_path, "left")
    right = _repo(tmp_path, "right")
    payload(mdf(python_exe, "integrate", "init", "--repo", str(left)))
    payload(mdf(python_exe, "integrate", "init", "--repo", str(right)))
    again = payload(mdf(python_exe, "integrate", "init", "--repo", str(left)))
    assert again["token"] and not again["token"].startswith("-")
    assert ".integration/" in (left / ".gitignore").read_text(encoding="utf-8")
    git(left, "check-ignore", ".integration/inbox/note.yaml")
    payload(
        mdf(
            python_exe, "integrate", "peer", "--repo", str(left),
            "--name", "right", "--target", str(right),
        )
    )
    proc = _poll_proc(python_exe, right)
    try:
        waiting = _next_event(proc)
        assert waiting["event"] == "waiting"
        assert waiting["ok"] is True
        sent = payload(
            mdf(
                python_exe, "integrate", "send", "--repo", str(left),
                "--to", "right", "--body", "看到超时",
            )
        )
        assert sent["kind"] == "send"
        assert sent["transport"] == "path"
        message = _next_message(proc)
        assert message["body"] == "看到超时"
        assert message["kind"] == "send"
        assert message["from"]["repo"] == "left"
        assert message["token"] == again["token"]
        assert proc.poll() is None
    finally:
        _stop(proc)


def test_poll_timeout_exits_after_waiting(tmp_path: Path, python_exe: str) -> None:
    repo = _repo(tmp_path, "solo")
    payload(mdf(python_exe, "integrate", "init", "--repo", str(repo)))
    proc = _poll_proc(python_exe, repo, "--timeout", "0.3")
    try:
        waiting = _next_event(proc)
        assert waiting["event"] == "waiting"
        timed_out = _next_event(proc)
        assert timed_out["event"] == "timeout"
        assert timed_out["message"] is None
        proc.wait(timeout=2)
        assert proc.returncode == 0
    finally:
        _stop(proc)


def test_bug_request_requires_fields_and_round_trips(tmp_path: Path, python_exe: str) -> None:
    left = _repo(tmp_path, "left")
    right = _repo(tmp_path, "right")
    for repo in (left, right):
        payload(mdf(python_exe, "integrate", "init", "--repo", str(repo)))
    payload(
        mdf(
            python_exe, "integrate", "peer", "--repo", str(left),
            "--name", "right", "--target", str(right),
        )
    )
    missing = mdf(
        python_exe, "integrate", "send", "--repo", str(left),
        "--to", "right", "--kind", "bug-request", "--body", "不完整",
    )
    assert missing.returncode == 1
    assert json.loads(missing.stderr)["error"] == "bad_message"
    payload(
        mdf(
            python_exe, "integrate", "send", "--repo", str(left),
            "--to", "right", "--kind", "bug-request", "--reply-to", "earlier",
            "--observed", "超时", "--expected", "成功",
            "--repro", "调用一次", "--impact", "联调阻断",
        )
    )
    proc = _poll_proc(python_exe, right)
    try:
        got = _next_message(proc)
        assert got["reply_to"] == "earlier"
        assert got["body"]["observed"] == "超时"
        assert got["body"]["impact"] == "联调阻断"
    finally:
        _stop(proc)


def test_branch_name_resolves_to_worktree(tmp_path: Path, python_exe: str) -> None:
    repo = _repo(tmp_path, "repo")
    other = tmp_path / "feature-demo"
    git(repo, "worktree", "add", "-b", "feature/demo", str(other))
    payload(mdf(python_exe, "integrate", "init", "--repo", str(repo)))
    payload(mdf(python_exe, "integrate", "init", "--repo", str(other)))
    added = payload(
        mdf(
            python_exe, "integrate", "peer", "--repo", str(repo),
            "--name", "demo", "--target", "feature/demo",
        )
    )
    assert added["peer"]["path"] == str(other.resolve())
    payload(
        mdf(
            python_exe, "integrate", "send", "--repo", str(repo),
            "--to", "demo", "--body", "在分支上",
        )
    )
    proc = _poll_proc(python_exe, other)
    try:
        assert _next_message(proc)["body"] == "在分支上"
    finally:
        _stop(proc)


def test_http_requires_token_after_ping_and_end_keeps_listen(
    tmp_path: Path, python_exe: str
) -> None:
    sender = _repo(tmp_path, "sender")
    receiver = _repo(tmp_path, "receiver")
    payload(mdf(python_exe, "integrate", "init", "--repo", str(sender)))
    receiver_init = payload(
        mdf(python_exe, "integrate", "init", "--repo", str(receiver))
    )
    cli = skill_dir("mdf") / "scripts" / "mdf.py"
    proc = subprocess.Popen(
        [
            python_exe, str(cli), "integrate", "listen",
            "--repo", str(receiver), "--bind", "127.0.0.1:0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        started = _next_event(proc)
        payload(
            mdf(
                python_exe, "integrate", "peer", "--repo", str(sender),
                "--name", "remote", "--target", started["listen"],
            )
        )
        rejected = mdf(
            python_exe, "integrate", "send", "--repo", str(sender),
            "--to", "remote", "--body", "过早",
        )
        assert rejected.returncode == 1
        assert json.loads(rejected.stderr)["error"] == "auth_rejected"
        ping = payload(
            mdf(
                python_exe, "integrate", "send", "--repo", str(sender),
                "--to", "remote", "--kind", "ping",
            )
        )
        assert ping["transport"] == "http"
        payload(
            mdf(
                python_exe, "integrate", "peer", "--repo", str(sender),
                "--name", "remote", "--target", started["listen"],
                "--token", receiver_init["token"],
            )
        )
        payload(
            mdf(
                python_exe, "integrate", "send", "--repo", str(sender),
                "--to", "remote", "--body", "跨机器",
            )
        )
        poller = _poll_proc(python_exe, receiver)
        try:
            assert _next_message(poller)["kind"] == "ping"
            assert _next_message(poller)["body"] == "跨机器"
            payload(
                mdf(
                    python_exe, "integrate", "send", "--repo", str(sender),
                    "--to", "remote", "--kind", "end",
                )
            )
            assert proc.poll() is None
            payload(
                mdf(
                    python_exe, "integrate", "send", "--repo", str(sender),
                    "--to", "remote", "--body", "仍在监听",
                )
            )
            assert _next_message(poller)["kind"] == "end"
            assert _next_message(poller)["body"] == "仍在监听"
            assert poller.poll() is None
            status = payload(
                mdf(python_exe, "integrate", "status", "--repo", str(receiver))
            )
            assert status["listen"] == started["listen"]
            assert status["pending"] == 0
        finally:
            _stop(poller)
    finally:
        _stop(proc)
