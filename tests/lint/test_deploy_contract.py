"""内部 mdf-deploy Skill 把源仓库 HEAD 装进目标项目。"""
from __future__ import annotations
import ast
import sys
from _support import REPO_ROOT


SKILL = REPO_ROOT / ".agents" / "skills" / "mdf-deploy" / "SKILL.md"


def test_internal_skill_installs_into_the_project_cache() -> None:
    text = SKILL.read_text(encoding="utf-8")
    commands = text.split("## 命令", 1)[1]

    assert "name: mdf-deploy" in text
    assert "upgrade" in commands
    assert "--source" in commands
    assert "--repo" in commands
    assert "--expected-commit" in commands
    assert "mdf-deploy.sh" not in text
    assert "--home" not in commands
    assert not (REPO_ROOT / "mdf-deploy.sh").exists()
    for name in ("github-actions.yml", "gitlab-ci.yml"):
        template = (REPO_ROOT / "skills/mdf/assets/ci" / name).read_text(encoding="utf-8")
        assert "MDF_SKILL" not in template
        assert "MDF_HOME" not in template
        assert "mdf_launcher.py" not in template
        assert "MDF_REVISION" in template


def test_entry_template_is_stdlib_only() -> None:
    path = REPO_ROOT / "skills" / "mdf" / "assets" / "host" / "mdf_entry.py"
    text = path.read_text(encoding="utf-8")
    modules = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".", 1)[0])
    assert modules <= sys.stdlib_module_names
    assert "mdf_home" not in text and "mdf_core" not in text
    assert text.count('REVISION = ""') == 1
    assert text.count('SOURCE = ""') == 1
    skill = (REPO_ROOT / "skills" / "mdf" / "assets" / "host" / "SKILL.md").read_text(encoding="utf-8")
    assert "mdf_entry.py" in skill and "MDF_ROOT" in skill
    assert "git clone" not in skill and ".mdf/cache" not in skill
