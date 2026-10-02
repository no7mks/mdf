"""project-verify 的 stdout JSON、stderr 进度与错误输出。"""
from __future__ import annotations
import contextlib
import io
import json
import shlex
import sys
import time
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def link_bugfix_suite(work: Path) -> None:
    path = work / "changes/unreleased/bug-cd34/suites.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"suites": ["billing"]}) + "\n")


def last_json(stderr: str) -> dict:
    return json.loads(stderr.rstrip().splitlines()[-1])


def test_project_verify_stdout_stays_json_and_labels_item_id(
    python_exe, tmp_path
):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--bug", "bug-CD34",
        "--objectives-file", str(write_work_objectives(tmp_path)),
    ))
    work = Path(created["worktree"])
    link_bugfix_suite(work)
    commit(work, "test: suites")
    patch_module_command(work, "lint", lambda _: "echo OUT; echo ERR >&2")
    commit(work, "test: lint 输出")
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
        "--objectives-file", str(write_work_objectives(tmp_path)),
    ))
    work = Path(created["worktree"])
    link_bugfix_suite(work)
    commit(work, "test: suites")
    patch_module_command(work, "lint", lambda _: "printf no-newline; exit 1")
    commit(work, "test: lint 失败")
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
    lines = [
        f"[{index}/4] start {name}"
        for index, name in enumerate(
            ("lint:default", "build:default", "quick:default", "release:default"),
            1,
        )
    ]
    assert [result.stderr.index(line) for line in lines] == sorted(
        result.stderr.index(line) for line in lines
    )
