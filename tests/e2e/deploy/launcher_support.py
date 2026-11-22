"""仓外安装测试共用的临时 HOME、版本目录和上游仓库。"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from _support import REPO_ROOT, run
from mdf_test_support import init_git

SKILL = REPO_ROOT / "skills" / "mdf"
LAUNCHER = SKILL / "scripts" / "mdf_launcher.py"
REV_A = "a" * 40
REV_B = "b" * 40


def invoke(home: Path, args: list[str], *, mdf_home: str | None = None, path_first: bool = False):
    env = os.environ.copy()
    env["HOME"] = str(home)
    if mdf_home is None:
        env.pop("MDF_HOME", None)
    else:
        env["MDF_HOME"] = mdf_home
    if path_first:
        env["PATH"] = str(home / ".local" / "bin") + os.pathsep + env.get("PATH", "")
    return run(args, env=env)


def plant(root: Path, revision: str) -> Path:
    version = root / "versions" / revision
    scripts = version / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(LAUNCHER, scripts / "mdf_launcher.py")
    shutil.copy2(LAUNCHER.parent / "mdf_home.py", scripts / "mdf_home.py")
    (scripts / "mdf_launcher.py").chmod(0o755)
    (scripts / "mdf.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (version / "references").mkdir()
    (version / "references" / ".version").write_text(f"{revision}\n", encoding="utf-8")
    current = root / "current"
    if current.is_symlink() or current.exists():
        current.unlink()
    current.symlink_to(Path("versions") / revision)
    return version


def link_bin(home: Path, root: Path) -> Path:
    link = home / ".local" / "bin" / "mdf"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(root / "current" / "scripts" / "mdf_launcher.py")
    return link


def root_of(result) -> Path:
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    lines = result.stdout.splitlines()
    assert len(lines) == 1 and lines[0] != ""
    return Path(lines[0])


HOST_FOLDERS = (".agents", ".claude", ".kiro", ".openclaw")


def assert_host_copies(home: Path, version: Path) -> None:
    expected = {
        "SKILL.md": version / "assets" / "host" / "SKILL.md",
        "agents/openai.yaml": version / "agents" / "openai.yaml",
        "scripts/mdf_launcher.py": version / "scripts" / "mdf_launcher.py",
        "scripts/mdf_home.py": version / "scripts" / "mdf_home.py",
    }
    for folder in HOST_FOLDERS:
        base = home / folder / "skills" / "mdf"
        assert base.is_dir() and not base.is_symlink()
        for relative, source in expected.items():
            path = base / relative
            assert path.is_file() and not path.is_symlink()
            assert path.read_bytes() == source.read_bytes()


def plant_host(home: Path, version: Path) -> Path:
    dest = home / ".agents" / "skills" / "mdf" / "scripts"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("mdf_launcher.py", "mdf_home.py"):
        shutil.copy2(version / "scripts" / name, dest / name)
    return dest / "mdf_launcher.py"


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
