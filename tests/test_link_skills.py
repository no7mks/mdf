"""安装器的当前 skill set 替换行为。"""

from __future__ import annotations

import os
from pathlib import Path

from _support import REPO_ROOT, run


def test_install_replaces_mdf_skills_and_preserves_repository_artifacts(
    tmp_path: Path,
):
    target_repo = tmp_path / "target"
    skills_dir = target_repo / ".codex" / "skills"
    skills_dir.mkdir(parents=True)
    retired = skills_dir / "mdf-retired"
    retired.mkdir()
    (retired / "old.txt").write_text("retired\n", encoding="utf-8")
    (skills_dir / "mdf").write_text("stale\n", encoding="utf-8")
    (skills_dir / "other-skill").mkdir()

    manifest = target_repo / ".mdf" / "manifest.yaml"
    manifest.parent.mkdir()
    manifest.write_text("state: ready\n", encoding="utf-8")
    fact = target_repo / "docs" / "product.md"
    fact.parent.mkdir()
    fact.write_text("# Product\n", encoding="utf-8")

    command = [
        "sh",
        str(REPO_ROOT / "link_skills.sh"),
        "codex",
        "--project",
        str(target_repo),
    ]
    installed = run(command)
    assert installed.returncode == 0, installed.stderr
    assert not retired.exists()
    assert (skills_dir / "mdf").is_dir()
    assert not (skills_dir / "mdf").is_symlink()
    assert (skills_dir / "other-skill").is_dir()

    assert sorted(path.name for path in skills_dir.glob("mdf*")) == ["mdf"]
    assert manifest.read_text(encoding="utf-8") == "state: ready\n"
    assert fact.read_text(encoding="utf-8") == "# Product\n"

    upgraded = run(command)
    assert upgraded.returncode == 0, upgraded.stderr
    assert "已卸载" in upgraded.stdout


def test_list_works_from_the_skill_source_repository():
    listed = run(["sh", "./link_skills.sh", "--list"], cwd=REPO_ROOT)

    assert listed.returncode == 0, listed.stderr
    assert "已知 agent" in listed.stdout
    assert "codex" in listed.stdout
    assert "kimi" in listed.stdout


def test_global_dry_run_visits_every_known_agent(tmp_path: Path):
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    preview = run(
        ["sh", str(REPO_ROOT / "link_skills.sh"), "--global", "--dry-run"],
        env=env,
    )

    assert preview.returncode == 0, preview.stderr
    for agent in ("claude", "cursor", "kiro", "codex", "kimi", "openclaw"):
        assert f"[{agent}]" in preview.stdout


def test_kimi_install_uses_project_skill_directory(tmp_path: Path):
    target_repo = tmp_path / "target"
    target_repo.mkdir()

    installed = run(
        [
            "sh",
            str(REPO_ROOT / "link_skills.sh"),
            "kimi-code",
            "--project",
            str(target_repo),
        ]
    )

    assert installed.returncode == 0, installed.stderr
    installed_skill = target_repo / ".agents" / "skills" / "mdf"
    assert installed_skill.is_dir()
    assert not installed_skill.is_symlink()
