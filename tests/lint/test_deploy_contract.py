"""内部 mdf-deploy Skill 列出的命令。"""
from __future__ import annotations
import shutil
from pathlib import Path
from _support import REPO_ROOT, run
from mdf_test_support import init_git


SKILL = REPO_ROOT / ".agents" / "skills" / "mdf-deploy" / "SKILL.md"


def test_internal_skill_installs_outside_the_repo() -> None:
    text = SKILL.read_text(encoding="utf-8")
    commands = text.split("## 命令", 1)[1]

    assert "name: mdf-deploy" in text
    assert " install" in commands
    assert "--home" in commands
    assert "diff" not in commands
    assert "unistall" not in text
    assert 'mdf-deploy.sh" merge' not in text
    assert not (REPO_ROOT / "redeploy_mdf.sh").exists()
    assert not (REPO_ROOT / ".agents" / "skills" / "mdf-redeploy").exists()
    for name in ("github-actions.yml", "gitlab-ci.yml"):
        template = (REPO_ROOT / "skills/mdf/assets/ci" / name).read_text(encoding="utf-8")
        assert "MDF_SKILL" not in template
        assert "MDF_HOME" in template
        assert "mdf_launcher.py" in template
