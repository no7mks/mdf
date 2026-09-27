"""Shared helpers for the skills test-suite.

Skill discovery lets structural tests iterate over every skill in the repo,
so a newly added skill is validated automatically.
"""

from __future__ import annotations

import subprocess
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
