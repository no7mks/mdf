"""Pytest fixtures shared across the skills test-suite."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from _support import REPO_ROOT, Skill, discover_skills

# Make the venv interpreter that runs pytest the one the tests shell out to.
PYTHON = sys.executable

# 临时仓库与被测 CLI 的提交身份统一由环境提供，省去逐仓库 git config。
for _key in ("GIT_AUTHOR", "GIT_COMMITTER"):
    os.environ.setdefault(f"{_key}_NAME", "MDF Test")
    os.environ.setdefault(f"{_key}_EMAIL", "mdf@example.invalid")


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


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """每次运行都写 JUnit XML：优先 MDF_REPORT_DIR，否则 .test-reports/<时间戳>/。"""
    if config.option.xmlpath:
        return
    root = os.environ.get("MDF_REPORT_DIR")
    if not root:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        root = str(REPO_ROOT / ".test-reports" / f"{stamp}-{os.getpid()}")
    config.option.xmlpath = str(Path(root) / "junit.xml")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """skipped、xfailed 与 xpassed 都使本次运行失败。"""
    terminal = session.config.pluginmanager.get_plugin("terminalreporter")
    stats = terminal.stats if terminal else {}
    if (any(stats.get(key) for key in ("skipped", "xfailed", "xpassed"))
            and exitstatus == pytest.ExitCode.OK):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
