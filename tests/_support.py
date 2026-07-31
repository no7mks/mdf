"""Shared helpers for the skills test-suite.

Two responsibilities:

1. Skill discovery  -> lets structural tests iterate over every skill in the
   repo, so a newly added skill is validated automatically.
2. Capability probing -> lets functional tests skip cleanly when an optional
   external tool (LibreOffice, poppler, a global npm package, ...) is missing,
   instead of failing on a machine that simply lacks that tool.
"""

from __future__ import annotations

import functools
import importlib.util
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
# Skills that live outside the public `skills/` tree but still ship a SKILL.md.
EXTRA_SKILL_ROOTS = [REPO_ROOT / ".kiro" / "skills"]


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


# ---------------------------------------------------------------------------
# Capability probing (cached so tests stay fast)
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=None)
def has_module(module: str) -> bool:
    """True if a Python module is importable in the current interpreter."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


@functools.lru_cache(maxsize=None)
def has_command(command: str) -> bool:
    """True if an executable is on PATH."""
    return shutil.which(command) is not None


@functools.lru_cache(maxsize=None)
def has_soffice() -> bool:
    """LibreOffice, either on PATH or at the standard macOS app location."""
    if has_command("soffice") or has_command("libreoffice"):
        return True
    mac_path = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    return mac_path.exists()


@functools.lru_cache(maxsize=None)
def node_global_path() -> str | None:
    """Return the global npm modules directory, or None if npm is absent."""
    if not has_command("npm"):
        return None
    try:
        out = subprocess.run(
            ["npm", "root", "-g"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    path = out.stdout.strip()
    return path or None


@functools.lru_cache(maxsize=None)
def has_node_package(package: str) -> bool:
    """True if a package is installed in the global npm modules directory."""
    root = node_global_path()
    if root is None:
        return False
    return (Path(root) / package).exists()


def node_env() -> dict[str, str]:
    """An environment dict with NODE_PATH pointing at global modules."""
    env = dict(os.environ)
    root = node_global_path()
    if root:
        existing = env.get("NODE_PATH", "")
        env["NODE_PATH"] = f"{root}{os.pathsep}{existing}" if existing else root
    return env


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run with sane defaults for the test-suite."""
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 120)
    return subprocess.run(cmd, **kwargs)
