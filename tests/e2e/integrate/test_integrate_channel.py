"""联调 inbox 与可选 HTTP。"""
from __future__ import annotations
import json
import queue
import re
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
    proc = subprocess.Popen(
        [
            python_exe, str(cli), "integrate", "poll",
            "--repo", str(repo), *extra,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**__import__("os").environ, "PYTHONUNBUFFERED": "1"},
    )
    _lines(proc)
    return proc


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


def _next_line(proc: subprocess.Popen, timeout: float = 5) -> str:
    assert proc.stdout is not None
    try:
        line = _lines(proc).get(timeout=timeout)
    except queue.Empty:
        raise AssertionError("poll 没有输出") from None
    assert line, "poll stdout 关闭"
    return line.rstrip("\n")


def _next_json(proc: subprocess.Popen, timeout: float = 5) -> dict:
    return json.loads(_next_line(proc, timeout=timeout))


def _next_wait(proc: subprocess.Popen, timeout: float = 5) -> str:
    line = _next_line(proc, timeout=timeout)
    assert "等待" in line, line
    return line


def _next_received(proc: subprocess.Popen, timeout: float = 5) -> str:
    deadline = time.monotonic() + timeout
    header = ""
    body: list[str] = []
    while time.monotonic() < deadline:
        line = _next_line(proc, timeout=max(0.05, deadline - time.monotonic()))
        if not header:
            if not line or ("等待" in line and "收到" not in line):
                continue
            assert "收到" in line, line
            header = line
            continue
        if line == "":
            break
        body.append(line)
    assert header, "poll 没有交出消息"
    return header + ("\n" + "\n".join(body) if body else "")


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
        _next_wait(proc)
        sent = mdf(
            python_exe, "integrate", "send", "--repo", str(left),
            "--to", "right", "--body", "看到超时",
        )
        assert_ok(sent)
        assert "发出  left/main -> right  send" in sent.stdout
        assert "看到超时" in sent.stdout
        assert "{" not in sent.stdout
        got = _next_received(proc)
        assert "收到  left/main -> right  send" in got
        assert "看到超时" in got
        assert "{" not in got
        assert proc.poll() is None
        inbox = next((right / ".integration" / "inbox").glob("*.yaml"))
        assert again["token"] in inbox.read_text(encoding="utf-8")
    finally:
        _stop(proc)


def test_status_reply_can_use_ids_from_shell_output(tmp_path: Path, python_exe: str) -> None:
    left, right = _repo(tmp_path, "left"), _repo(tmp_path, "right")
    for repo, name, target in ((left, "right", right), (right, "left", left)):
        payload(mdf(python_exe, "integrate", "init", "--repo", str(repo)))
        payload(mdf(python_exe, "integrate", "peer", "--repo", str(repo),
                    "--name", name, "--target", str(target)))
    left_poll, right_poll = _poll_proc(python_exe, left), _poll_proc(python_exe, right)
    try:
        _next_wait(left_poll)
        _next_wait(right_poll)
        sent = mdf(python_exe, "integrate", "send", "--repo", str(left), "--to", "right",
                   "--body", "状态询问：本侧在测接口；请确认当前工作")
        assert sent.returncode == 0
        request_id = re.search(r"\bid=([^\s]+)", sent.stdout).group(1)
        received = _next_received(right_poll)
        assert f"id={request_id}" in received
        reply = mdf(python_exe, "integrate", "send", "--repo", str(right), "--to", "left",
                    "--reply-to", request_id, "--body", "状态回复：本侧服务已就绪")
        assert reply.returncode == 0
        assert f"reply_to={request_id}" in _next_received(left_poll)
        assert left_poll.poll() is None and right_poll.poll() is None
    finally:
        _stop(left_poll)
        _stop(right_poll)


def test_poll_timeout_exits_after_waiting(tmp_path: Path, python_exe: str) -> None:
    repo = _repo(tmp_path, "solo")
    payload(mdf(python_exe, "integrate", "init", "--repo", str(repo)))
    proc = _poll_proc(python_exe, repo, "--timeout", "0.3")
    try:
        _next_wait(proc)
        timed_out = _next_line(proc)
        assert "超时" in timed_out
        proc.wait(timeout=2)
        assert proc.returncode == 0
    finally:
        _stop(proc)


def test_poll_heartbeats_peer_after_each_wait(tmp_path: Path, python_exe: str) -> None:
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
    proc = _poll_proc(
        python_exe, left, "--wait", "0.2", "--timeout", "0.7",
    )
    try:
        _next_wait(proc)
        found = ""
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            line = _next_line(proc, timeout=1)
            if "发出" in line and "heartbeat" in line:
                found = line
                break
        assert found
        inbox = list((right / ".integration" / "inbox").glob("*.yaml"))
        assert inbox
        assert "heartbeat" in inbox[0].read_text(encoding="utf-8")
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
    sent = mdf(
        python_exe, "integrate", "send", "--repo", str(left),
        "--to", "right", "--kind", "bug-request", "--reply-to", "earlier",
        "--observed", "超时", "--expected", "成功",
        "--repro", "调用一次", "--impact", "联调阻断",
    )
    assert_ok(sent)
    assert "发出" in sent.stdout and "bug-request" in sent.stdout
    proc = _poll_proc(python_exe, right)
    try:
        got = _next_received(proc)
        assert "收到" in got and "bug-request" in got
        assert "observed: 超时" in got
        assert "impact: 联调阻断" in got
        inbox = next((right / ".integration" / "inbox").glob("*.yaml"))
        assert "earlier" in inbox.read_text(encoding="utf-8")
    finally:
        _stop(proc)


def test_courtesy_requires_ack_with_reply_to(tmp_path: Path, python_exe: str) -> None:
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
    payload(
        mdf(
            python_exe, "integrate", "peer", "--repo", str(right),
            "--name", "left", "--target", str(left),
        )
    )
    missing = mdf(
        python_exe, "integrate", "send", "--repo", str(right),
        "--to", "left", "--kind", "ack",
    )
    assert missing.returncode == 1
    assert json.loads(missing.stderr)["error"] == "bad_message"
    sent = mdf(
        python_exe, "integrate", "send", "--repo", str(left),
        "--to", "right", "--kind", "courtesy",
    )
    assert_ok(sent)
    assert "发出" in sent.stdout and "courtesy" in sent.stdout
    inbox = next((right / ".integration" / "inbox").glob("*.yaml"))
    courtesy_id = inbox.read_text(encoding="utf-8").split("id:", 1)[1].splitlines()[0]
    courtesy_id = courtesy_id.strip().strip('"')
    proc = _poll_proc(python_exe, right)
    try:
        got = _next_received(proc)
        assert "收到" in got and "courtesy" in got
        acked = mdf(
            python_exe, "integrate", "send", "--repo", str(right),
            "--to", "left", "--kind", "ack", "--reply-to", courtesy_id,
        )
        assert_ok(acked)
        assert "发出" in acked.stdout and "ack" in acked.stdout
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
    sent = mdf(
        python_exe, "integrate", "send", "--repo", str(repo),
        "--to", "demo", "--body", "在分支上",
    )
    assert_ok(sent)
    assert "在分支上" in sent.stdout
    proc = _poll_proc(python_exe, other)
    try:
        assert "在分支上" in _next_received(proc)
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
        started = _next_json(proc)
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
        ping = mdf(
            python_exe, "integrate", "send", "--repo", str(sender),
            "--to", "remote", "--kind", "ping",
        )
        assert_ok(ping)
        assert "发出" in ping.stdout and "ping" in ping.stdout
        payload(
            mdf(
                python_exe, "integrate", "peer", "--repo", str(sender),
                "--name", "remote", "--target", started["listen"],
                "--token", receiver_init["token"],
            )
        )
        sent = mdf(
            python_exe, "integrate", "send", "--repo", str(sender),
            "--to", "remote", "--body", "跨机器",
        )
        assert_ok(sent)
        poller = _poll_proc(python_exe, receiver)
        try:
            first = _next_received(poller)
            assert "ping" in first
            assert "跨机器" in _next_received(poller)
            ended = mdf(
                python_exe, "integrate", "send", "--repo", str(sender),
                "--to", "remote", "--kind", "end",
            )
            assert_ok(ended)
            assert proc.poll() is None
            again = mdf(
                python_exe, "integrate", "send", "--repo", str(sender),
                "--to", "remote", "--body", "仍在监听",
            )
            assert_ok(again)
            assert "end" in _next_received(poller)
            assert "仍在监听" in _next_received(poller)
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
