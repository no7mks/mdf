"""verification command 的流式 stderr 进度与 bounded tail。"""
from __future__ import annotations

import contextlib
import io
import json
import shlex
import sys
import time

from mdf_test_support import *  # noqa: F403
from test_mdf_gitflow_delivery import start_repo


def py_c(code: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def link_bugfix_suite(work: Path) -> None:
    path = work / "changes/unreleased/bug-cd34/suites.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"suites": ["billing"]}) + "\n")


def last_json(stderr: str) -> dict:
    return json.loads(stderr.rstrip().splitlines()[-1])


def run_captured(repo, command, **kwargs):
    load_core_module()
    from mdf_core.errors import MDFError
    from mdf_core.verify_run import run_verify_command

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        try:
            result = run_verify_command(repo, command, **kwargs)
            error = None
        except MDFError as exc:
            result = None
            error = exc
    return result, error, buf.getvalue()


def test_progress_label_uses_first_line_and_truncates():
    load_core_module()
    from mdf_core.verify_run import _progress_label

    assert _progress_label("alpha\nbeta") == "alpha"
    assert _progress_label("x" * 200) == "x" * 80


def test_success_tees_stdout_and_stderr_and_keeps_result_shape(tmp_path):
    command = py_c(
        "import sys; sys.stdout.write('OUT\\n'); sys.stderr.write('ERR\\n')"
    )
    result, error, text = run_captured(
        tmp_path, command, label="io", index=2, total=5
    )
    assert error is None
    assert result == {"command": command, "exit_code": 0}
    assert "OUT" in text
    assert "ERR" in text
    assert "[2/5] start io" in text
    assert "done exit=0" in text
    assert "[2/5] start io" in text.split("OUT")[0]


def test_failure_tails_are_bounded_and_stderr_gets_child_output(tmp_path):
    command = py_c(
        "import sys; sys.stdout.write('x' * 3000); sys.exit(1)"
    )
    result, error, text = run_captured(tmp_path, command, label="fail")
    assert result is None
    assert error is not None
    assert error.code == "verify_command_failed"
    tail = error.details["stdout_tail"]
    assert tail == "x" * 2000
    assert "x" * 50 in text
    assert "[1/1] start fail" in text
    assert "done exit=1" in text


def test_missing_newline_is_flushed_before_done(tmp_path):
    command = py_c(
        "import sys; sys.stdout.write('no newline'); sys.exit(1)"
    )
    _, error, text = run_captured(tmp_path, command, label="raw")
    assert error is not None
    assert error.details["stdout_tail"] == "no newline"
    assert "no newline\n" in text
    done_at = text.rfind("[1/1] done exit=1")
    assert done_at > text.find("no newline")
    assert text[done_at - 1] == "\n"


def test_utf8_chunks_are_not_replaced(tmp_path):
    command = py_c("import sys; sys.stdout.write('测' * 40000)")
    result, error, text = run_captured(tmp_path, command, label="zh")
    assert error is None
    assert result["exit_code"] == 0
    assert "\ufffd" not in text
    assert "测" * 20 in text


def test_batch_fail_fast_skips_later_commands(tmp_path):
    load_core_module()
    from mdf_core.errors import MDFError
    from mdf_core.verify_run import run_verify_commands

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        try:
            run_verify_commands(
                tmp_path,
                ["true", "false", "true"],
                labels=["keep", "fail", "skip"],
            )
        except MDFError as exc:
            error = exc
        else:
            raise AssertionError("expected failure")
    text = buf.getvalue()
    assert error.details["results"] == [
        {"command": "true", "exit_code": 0},
        {"command": "false", "exit_code": 1},
    ]
    assert "[1/3] start keep" in text
    assert "[2/3] start fail" in text
    assert "[3/3]" not in text


def test_timeout_includes_partial_tail_and_returns_promptly(tmp_path):
    command = py_c(
        "import sys, time; sys.stdout.write('partial'); "
        "sys.stdout.flush(); time.sleep(10)"
    )
    started = time.monotonic()
    _, error, text = run_captured(
        tmp_path, command, label="sleep", timeout=0.4
    )
    elapsed = time.monotonic() - started
    assert elapsed < 6
    assert error is not None
    assert error.details["timeout_seconds"] == 0.4
    assert "partial" in error.details["stdout_tail"]
    assert "done exit=" in text


def test_heartbeat_when_child_is_silent(tmp_path, monkeypatch):
    load_core_module()
    from mdf_core import verify_run

    monkeypatch.setattr(verify_run, "HEARTBEAT_SECONDS", 0.1)
    command = py_c("import time; time.sleep(0.45)")
    _, error, text = run_captured(
        tmp_path, command, label="wait", timeout=2
    )
    assert error is None
    assert "[1/1] running wait" in text


def test_project_verify_stdout_stays_json_and_labels_item_id(
    python_exe, tmp_path
):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--bug", "bug-CD34",
    ))
    work = Path(created["worktree"])
    link_bugfix_suite(work)
    manifest = work / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        'lint: "true"',
        'lint: "echo OUT; echo ERR >&2"',
    ))
    result = mdf(python_exe, "project-verify", "run", "--repo", str(work))
    payload(result)
    stdout_lines = result.stdout.splitlines()
    assert len(stdout_lines) == 1
    assert "\nOUT\n" in f"\n{result.stderr}"
    assert "ERR" in result.stderr
    assert "[1/4] start lint" in result.stderr
    assert "done exit=0" in result.stderr


def test_project_verify_error_json_is_last_stderr_line(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--bug", "bug-CD34",
    ))
    work = Path(created["worktree"])
    link_bugfix_suite(work)
    manifest = work / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        'lint: "true"',
        'lint: "printf no-newline; exit 1"',
    ))
    result = mdf(python_exe, "project-verify", "run", "--repo", str(work))
    assert result.returncode != 0
    error = last_json(result.stderr)
    assert error["error"] == "verify_command_failed"
    assert "no-newline" in result.stderr


def test_project_verify_progress_uses_global_total(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "release",
        "--version", "1.3.0", "--objectives-file",
        str(write_release_objectives(tmp_path)),
    ))
    work = Path(created["worktree"])
    result = mdf(python_exe, "project-verify", "run", "--repo", str(work))
    payload(result)
    lines = [f"[{index}/4] start {name}"
             for index, name in enumerate(("lint", "build", "quick", "release"), 1)]
    assert [result.stderr.index(line) for line in lines] == sorted(
        result.stderr.index(line) for line in lines
    )
