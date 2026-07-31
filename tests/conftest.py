"""Pytest fixtures shared across the skills test-suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from _support import REPO_ROOT, Skill, discover_skills

# Make the venv interpreter that runs pytest the one the tests shell out to.
PYTHON = sys.executable


def skill_dir(name: str) -> Path:
    """Return a skill directory's absolute path for functional tests."""
    for skill in discover_skills():
        if skill.name == name:
            return skill.path
    raise LookupError(f"skill {name!r} not found under {REPO_ROOT}")


@pytest.fixture(scope="session")
def python_exe() -> str:
    return PYTHON


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    """A clean temp directory for a single test's artifacts."""
    return tmp_path


def pytest_generate_tests(metafunc):
    """Parametrize any test asking for a `skill` argument over all skills."""
    if "skill" in metafunc.fixturenames:
        skills = discover_skills()
        metafunc.parametrize("skill", skills, ids=[s.name for s in skills])
