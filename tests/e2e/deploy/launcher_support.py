"""项目本体缓存测试共用的临时 HOME 和上游仓库。"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from _support import REPO_ROOT, run
from mdf_test_support import init_git

SKILL = REPO_ROOT / "skills" / "mdf"


def invoke(home: Path, args: list[str], *, cwd: Path | None = None, mdf_home: str | None = None):
    env = os.environ.copy()
    env["HOME"] = str(home)
    if mdf_home is None:
        env.pop("MDF_HOME", None)
    else:
        env["MDF_HOME"] = mdf_home
    if cwd is None:
        cwd = home if home.is_dir() else home.parent
    return run(args, env=env, cwd=cwd)


def payload(result) -> dict:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def error(result) -> dict:
    assert result.returncode != 0, result.stdout
    assert result.stdout == ""
    return json.loads(result.stderr.strip().splitlines()[-1])


def copy_skill(dest: Path) -> None:
    shutil.copytree(
        SKILL, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def upstream(tmp_path: Path, name: str = "upstream") -> Path:
    source = tmp_path / name
    copy_skill(source / "skills" / "mdf")
    init_git(source)
    return source


def core_dir(project: Path) -> Path:
    return project / ".mdf" / "cache" / "mdf-core"


def assert_pointer(repo: Path, commit: str, source: str) -> None:
    base = repo / ".agents" / "skills" / "mdf"
    assert base.is_dir() and not base.is_symlink()
    names = sorted(path.name for path in base.iterdir())
    assert names == ["SKILL.md", "agents", "mdf_entry.py"]
    entry = base / "mdf_entry.py"
    text = entry.read_text(encoding="utf-8")
    assert f"REVISION = {json.dumps(commit)}" in text
    assert f"SOURCE = {json.dumps(source)}" in text
    assert (base / "SKILL.md").read_bytes() == (SKILL / "assets/host/SKILL.md").read_bytes()
