"""Shared helpers for the skills test-suite.

Skill discovery lets structural tests iterate over every skill in the repo,
so a newly added skill is validated automatically.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
# Skills that live outside the public `skills/` tree but still ship a SKILL.md.
EXTRA_SKILL_ROOTS = [
    REPO_ROOT / ".agents" / "skills",
    REPO_ROOT / ".kiro" / "skills",
]


@dataclass(frozen=True)
class Skill:
    """A discovered skill: a directory that contains a SKILL.md."""

    name: str  # directory name (e.g. "docx")
    path: Path  # skill directory
    skill_md: Path  # path to SKILL.md

    def __str__(self) -> str:  # nicer pytest test ids
        return self.name


def discover_skills() -> list[Skill]:
    """Find top-level skill directories containing a SKILL.md, sorted."""
    roots = [SKILLS_DIR, *EXTRA_SKILL_ROOTS]
    found: dict[str, Skill] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for skill_dir in root.iterdir():
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            found[skill_dir.name] = Skill(
                name=skill_dir.name, path=skill_dir, skill_md=skill_md
            )
    return [found[k] for k in sorted(found)]


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run with sane defaults for the test-suite."""
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 120)
    return subprocess.run(cmd, **kwargs)


def prefer_direct_git() -> None:
    """macOS 的系统 Git 是启动器；测试直接运行当前 toolchain 的同一 Git。"""
    if sys.platform != "darwin" or shutil.which("git") != "/usr/bin/git":
        return
    try:
        result = subprocess.run(
            ["/usr/bin/xcrun", "--find", "git"], capture_output=True, text=True, check=False,
        )
    except OSError:
        return
    executable = Path(result.stdout.strip())
    if (result.returncode or not executable.is_absolute() or executable == Path("/usr/bin/git")
            or not executable.is_file() or not os.access(executable, os.X_OK)):
        return
    os.environ["PATH"] = str(executable.parent) + os.pathsep + os.environ.get("PATH", os.defpath)


def isolate_test_temp_root() -> None:
    """保留 pytest 的清理策略，但只清理本 checkout 的临时仓库。"""
    if "PYTEST_DEBUG_TEMPROOT" in os.environ:
        return
    key = hashlib.sha256(str(REPO_ROOT.resolve()).encode()).hexdigest()[:12]
    root = Path(tempfile.gettempdir()) / f"mdf-pytest-{key}"
    root.mkdir(mode=0o700, exist_ok=True)
    os.environ["PYTEST_DEBUG_TEMPROOT"] = str(root)
