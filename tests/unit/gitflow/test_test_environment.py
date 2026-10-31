"""测试环境跳过 macOS Git 启动器，但保留用户选择和真实 Git。"""
import os
import subprocess
import pytest

import _support


def test_direct_git_is_visible_to_child_processes(tmp_path, monkeypatch):
    toolchain = tmp_path / "toolchain"
    toolchain.mkdir()
    executable = toolchain / "git"
    executable.write_text("#!/bin/sh\nprintf 'toolchain-git\\n'\n")
    executable.chmod(0o755)
    original = os.environ["PATH"]
    monkeypatch.setattr(_support.sys, "platform", "darwin")
    with monkeypatch.context() as patch:
        patch.setattr(_support.shutil, "which", lambda _: "/usr/bin/git")
        patch.setattr(_support.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
            a[0], 0, str(executable) + "\n", "",
        ))
        monkeypatch.setenv("PATH", original)
        _support.prefer_direct_git()
    assert os.environ["PATH"] == str(toolchain) + os.pathsep + original
    assert subprocess.run(["git", "--version"], capture_output=True, text=True, check=True).stdout == "toolchain-git\n"


@pytest.mark.parametrize("platform,git", [("linux", "/usr/bin/git"), ("darwin", "/custom/bin/git")])
def test_direct_git_keeps_other_platforms_and_user_selection(monkeypatch, platform, git):
    original = os.environ["PATH"]
    monkeypatch.setattr(_support.sys, "platform", platform)
    monkeypatch.setattr(_support.shutil, "which", lambda _: git)
    monkeypatch.setattr(_support.subprocess, "run", lambda *a, **k: pytest.fail("不应调用 xcrun"))
    _support.prefer_direct_git()
    assert os.environ["PATH"] == original


@pytest.mark.parametrize("failure", ["missing", "nonzero", "relative", "launcher", "not_executable"])
def test_direct_git_keeps_path_when_toolchain_is_unavailable(tmp_path, monkeypatch, failure):
    original = os.environ["PATH"]
    executable = tmp_path / "git"
    executable.write_text("not executable")
    monkeypatch.setattr(_support.sys, "platform", "darwin")
    monkeypatch.setattr(_support.shutil, "which", lambda _: "/usr/bin/git")

    def resolve(*args, **kwargs):
        if failure == "missing":
            raise FileNotFoundError("xcrun")
        path = {"relative": "git", "launcher": "/usr/bin/git"}.get(failure, str(executable))
        return subprocess.CompletedProcess(args[0], int(failure == "nonzero"), path, "")

    monkeypatch.setattr(_support.subprocess, "run", resolve)
    _support.prefer_direct_git()
    assert os.environ["PATH"] == original


def test_temp_cleanup_roots_are_isolated_between_checkouts(tmp_path, monkeypatch):
    monkeypatch.setattr(_support.tempfile, "gettempdir", lambda: str(tmp_path))
    roots = []
    for checkout in ("first", "second", "first"):
        monkeypatch.delenv("PYTEST_DEBUG_TEMPROOT", raising=False)
        monkeypatch.setattr(_support, "REPO_ROOT", tmp_path / checkout)
        _support.isolate_test_temp_root()
        root = _support.Path(os.environ["PYTEST_DEBUG_TEMPROOT"])
        assert root.is_dir() and root.parent == tmp_path
        roots.append(root)
    assert roots[0] == roots[2] and roots[0] != roots[1]


def test_temp_cleanup_honors_explicit_root(tmp_path, monkeypatch):
    root = tmp_path / "chosen"
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(root))
    _support.isolate_test_temp_root()
    assert os.environ["PYTEST_DEBUG_TEMPROOT"] == str(root)
