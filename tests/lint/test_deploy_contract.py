"""内部 mdf-deploy Skill 列出的命令。"""
from __future__ import annotations
import shutil
from pathlib import Path
from _support import REPO_ROOT, run
from mdf_test_support import init_git


SKILL = REPO_ROOT / ".agents" / "skills" / "mdf-deploy" / "SKILL.md"


def test_internal_skill_lists_the_three_commands() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "name: mdf-deploy" in text
    assert 'mdf-deploy.sh" merge' not in text
    assert not (REPO_ROOT / "redeploy_mdf.sh").exists()
    assert not (REPO_ROOT / ".agents" / "skills" / "mdf-redeploy").exists()
    for action in ("diff", "install", "unistall"):
        assert f" {action} " in text
