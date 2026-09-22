"""联调 inbox 与可选 HTTP。"""

from __future__ import annotations

import json
import select
import subprocess
from pathlib import Path

from conftest import skill_dir
from mdf_test_support import assert_ok, git, init_git, mdf, payload


def _repo(path: Path, name: str) -> Path:
    repo = path / name
    repo.mkdir()
    (repo / "README.md").write_text(f"{name}\n", encoding="utf-8")
    init_git(repo)
    return repo


def test_local_send_defaults_to_send_and_polls_once(tmp_path: Path, python_exe: str) -> None:
    left = _repo(tmp_path, "left")
    right = _repo(tmp_path, "right")
    payload(mdf(python_exe, "integrate", "init", "--repo", str(left)))
    payload(mdf(python_exe, "integrate", "init", "--repo", str(right)))
    again = payload(mdf(python_exe, "integrate", "init", "--repo", str(left)))
    assert again["token"]
    assert ".integration/" in (left / ".gitignore").read_text(encoding="utf-8")
    git(left, "check-ignore", ".integration/inbox/note.yaml")
    payload(
        mdf(
            python_exe, "integrate", "peer", "--repo", str(left),
            "--name", "right", "--target", str(right),
        )
    )
    sent = payload(
        mdf(
            python_exe, "integrate", "send", "--repo", str(left),
            "--to", "right", "--body", "看到超时",
        )
    )
    assert sent["kind"] == "send"
    assert sent["transport"] == "path"
    got = payload(
        mdf(python_exe, "integrate", "poll", "--repo", str(right), "--timeout", "2")
    )
    message = got["message"]
    assert message["body"] == "看到超时"
    assert message["kind"] == "send"
    assert message["from"]["repo"] == "left"
    assert message["token"] == again["token"]
    missed = payload(
        mdf(python_exe, "integrate", "poll", "--repo", str(right), "--timeout", "0.2")
    )
    assert missed["timeout"] is True
    assert missed["message"] is None


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
    got = payload(
        mdf(python_exe, "integrate", "poll", "--repo", str(right), "--timeout", "2")
    )
    body = got["message"]["body"]
    assert body["observed"] == "超时"
    assert body["impact"] == "联调阻断"
    assert got["message"]["reply_to"] == "earlier"


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
    got = payload(
        mdf(python_exe, "integrate", "poll", "--repo", str(other), "--timeout", "2")
    )
    assert got["message"]["body"] == "在分支上"


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
    assert proc.stdout is not None
    ready, _, _ = select.select([proc.stdout], [], [], 5)
    assert ready, "listen 没有打印地址"
    started = json.loads(proc.stdout.readline())
    try:
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
        first = payload(
            mdf(
                python_exe, "integrate", "poll", "--repo", str(receiver),
                "--timeout", "2",
            )
        )
        assert first["message"]["kind"] == "ping"
        second = payload(
            mdf(
                python_exe, "integrate", "poll", "--repo", str(receiver),
                "--timeout", "2",
            )
        )
        assert second["message"]["body"] == "跨机器"
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
        ended = payload(
            mdf(
                python_exe, "integrate", "poll", "--repo", str(receiver),
                "--timeout", "2",
            )
        )
        assert ended["message"]["kind"] == "end"
        later = payload(
            mdf(
                python_exe, "integrate", "poll", "--repo", str(receiver),
                "--timeout", "2",
            )
        )
        assert later["message"]["body"] == "仍在监听"
        status = payload(
            mdf(python_exe, "integrate", "status", "--repo", str(receiver))
        )
        assert status["listen"] == started["listen"]
        assert status["pending"] == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()
