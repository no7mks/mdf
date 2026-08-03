"""外部项目测试后的 MDF 审查与完整替换。"""

from __future__ import annotations

from pathlib import Path

import pytest

from _support import REPO_ROOT, run
from mdf_test_support import init_git


SCRIPT = REPO_ROOT / "redeploy_mdf.sh"
SKILL = REPO_ROOT / ".agents" / "skills" / "mdf-redeploy" / "SKILL.md"


def command(target: Path, action: str, *extra: str, agent: str = "codex"):
    return run(
        [
            "sh",
            str(SCRIPT),
            action,
            "--target",
            str(target),
            "--agent",
            agent,
            *extra,
        ]
    )


def test_internal_skill_controls_review_and_confirmation() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "name: mdf-redeploy" in text
    assert "redeploy_mdf.sh" in text
    assert "`kimi`" in text
    assert "用户明确确认" in text
    assert "不 patch、不部署" in text


def test_report_lists_target_changes_and_skill_difference(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("# target\n", encoding="utf-8")
    init_git(target)
    (target / "README.md").write_text("# changed\n", encoding="utf-8")
    (target / ".codex" / "skills" / "mdf").mkdir(parents=True)
    installed = target / ".codex" / "skills" / "mdf" / "local.md"
    installed.write_text("local change\n", encoding="utf-8")

    result = command(target, "report")

    assert result.returncode == 0, result.stderr
    assert "目标仓库 工作区改动：" in result.stdout
    assert "README.md" in result.stdout
    assert "Only in" in result.stdout
    assert "候选带回源仓库" in result.stdout
    assert "以当前源仓库 skills/mdf 为唯一真相" in result.stdout


def test_deploy_requires_explicit_confirmation_flag(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("# target\n", encoding="utf-8")
    init_git(target)

    result = command(target, "deploy")

    assert result.returncode != 0
    assert "deploy 需要 --yes" in result.stderr
    assert not (target / ".codex" / "skills" / "mdf").exists()


@pytest.mark.parametrize(
    ("agent", "skills_path"),
    [
        ("codex", ".codex/skills"),
        ("kimi-code", ".kimi-code/skills"),
    ],
)
def test_deploy_replaces_all_mdf_skills_and_preserves_artifacts(
    tmp_path: Path, agent: str, skills_path: str
):
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("# target\n", encoding="utf-8")
    init_git(target)
    skills = target / skills_path
    (skills / "mdf-retired").mkdir(parents=True)
    (skills / "mdf-retired" / "old.txt").write_text("old\n", encoding="utf-8")
    (skills / "mdf").mkdir()
    (skills / "mdf" / "old.txt").write_text("old\n", encoding="utf-8")
    (skills / "other-skill").mkdir()
    artifact = target / ".mdf" / "manifest.yaml"
    artifact.parent.mkdir()
    artifact.write_text("state: ready\n", encoding="utf-8")
    fact = target / "docs" / "current.md"
    fact.parent.mkdir()
    fact.write_text("# current\n", encoding="utf-8")

    result = command(target, "deploy", "--yes", agent=agent)

    assert result.returncode == 0, result.stderr
    assert not (skills / "mdf-retired").exists()
    assert (skills / "mdf").is_symlink()
    assert (skills / "other-skill").is_dir()
    assert artifact.read_text(encoding="utf-8") == "state: ready\n"
    assert fact.read_text(encoding="utf-8") == "# current\n"
