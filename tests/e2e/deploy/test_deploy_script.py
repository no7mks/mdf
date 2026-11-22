"""mdf-deploy.sh 只把当前 HEAD 装到本机版本目录。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from _support import REPO_ROOT, run
from launcher_support import assert_host_copies, error, payload, root_of
from mdf_test_support import init_git

SCRIPT = REPO_ROOT / "mdf-deploy.sh"


def init_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(SCRIPT, source / "mdf-deploy.sh")
    shutil.copytree(
        REPO_ROOT / "skills" / "mdf",
        source / "skills" / "mdf",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    os.chmod(source / "mdf-deploy.sh", 0o755)
    init_git(source)
    return source


def install(source: Path, home: Path, *, mdf_home: str | None = None):
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["MDF_PYTHON"] = sys.executable
    if mdf_home is None:
        env.pop("MDF_HOME", None)
    else:
        env["MDF_HOME"] = mdf_home
    return run(["sh", str(source / "mdf-deploy.sh"), "install"], env=env, cwd=source)


def test_script_rejects_removed_actions() -> None:
    for action in ("merge", "diff", "unistall"):
        result = run(["sh", str(SCRIPT), action])
        assert result.returncode != 0
        assert f"未知动作: {action}" in result.stderr


def test_install_archives_head_and_writes_hosts(tmp_path: Path) -> None:
    source = init_source(tmp_path)
    home = tmp_path / "home"
    result = install(source, home)
    assert result.returncode == 0, result.stderr
    revision = run(["git", "-C", str(source), "rev-parse", "HEAD"]).stdout.strip()
    root = home / ".local" / "share" / "mdf"
    version = root / "versions" / revision
    assert (version / "references" / ".version").read_text() == f"{revision}\n"
    assert os.readlink(root / "current") == f"versions/{revision}"
    assert (version / "SKILL.md").read_text() == (source / "skills" / "mdf" / "SKILL.md").read_text()
    host = (home / ".agents" / "skills" / "mdf" / "SKILL.md").read_text()
    assert "scripts/mdf_launcher.py" in host
    for banned in ("MDF_HOME", ".local/", ".mdf/logs", "mdf root"):
        assert banned not in host
    assert_host_copies(home, version)
    assert not (home / ".codex" / "skills" / "mdf").exists()
    assert not (home / ".cursor" / "skills" / "mdf").exists()
    link = home / ".local" / "bin" / "mdf"
    assert link.is_symlink()
    link.unlink()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("MDF_HOME", None)
    env["MDF_PYTHON"] = sys.executable
    found = root_of(run(
        [sys.executable, "-B", str(home / ".agents/skills/mdf/scripts/mdf_launcher.py"), "root"],
        env=env,
    ))
    assert found == version.resolve()


def test_install_requires_clean_source(tmp_path: Path) -> None:
    source = init_source(tmp_path)
    (source / "skills" / "mdf" / "SKILL.md").write_text("changed\n", encoding="utf-8")
    result = install(source, tmp_path / "home")
    assert result.returncode != 0
    assert "工作区不干净" in result.stderr
    assert not (tmp_path / "home" / ".local" / "share" / "mdf" / "current").exists()


def test_repeat_install_keeps_the_same_revision(tmp_path: Path) -> None:
    source = init_source(tmp_path)
    home = tmp_path / "home"
    assert install(source, home).returncode == 0
    again = install(source, home)
    data = payload(again)
    assert data["created"] is False
    assert data["revision"] == run(["git", "-C", str(source), "rev-parse", "HEAD"]).stdout.strip()


def test_install_home_flag_overrides_invalid_env(tmp_path: Path) -> None:
    source = init_source(tmp_path)
    home = tmp_path / "home"
    chosen = tmp_path / "opt"
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["MDF_HOME"] = ""
    env["MDF_PYTHON"] = sys.executable
    result = run(
        ["sh", str(source / "mdf-deploy.sh"), "install", "--home", str(chosen)],
        env=env, cwd=source,
    )
    assert result.returncode == 0, result.stderr
    assert (chosen / "current").is_symlink()
    body = error(run(
        [sys.executable, "-B", str(LAUNCHER_OF(source)), "root"],
        env=env,
    ))
    assert body["error"] == "mdf_home_invalid"


def test_empty_home_flag_does_not_fall_back(tmp_path: Path) -> None:
    source = init_source(tmp_path)
    home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["MDF_PYTHON"] = sys.executable
    env.pop("MDF_HOME", None)
    result = run(
        ["sh", str(source / "mdf-deploy.sh"), "install", "--home", ""],
        env=env, cwd=source,
    )
    assert result.returncode != 0
    assert "mdf_home_invalid" in result.stderr
    assert not (home / ".local" / "share" / "mdf" / "current").exists()


def test_relative_home_installs_an_absolute_launcher(tmp_path: Path) -> None:
    source = init_source(tmp_path)
    home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["MDF_PYTHON"] = sys.executable
    env.pop("MDF_HOME", None)
    result = run(
        ["sh", str(source / "mdf-deploy.sh"), "install", "--home", "opt/mdf"],
        env=env, cwd=source,
    )
    assert result.returncode == 0, result.stderr
    link = os.readlink(home / ".local" / "bin" / "mdf")
    assert Path(link).is_absolute()
    assert Path(link).is_file()
    assert (source / "opt" / "mdf" / "current").is_symlink()


def LAUNCHER_OF(source: Path) -> Path:
    return source / "skills" / "mdf" / "scripts" / "mdf_launcher.py"
    return source / "skills" / "mdf" / "scripts" / "mdf_launcher.py"
