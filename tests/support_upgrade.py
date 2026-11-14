"""upgrade 类 E2E 共用的上游与已安装目标仓库准备。"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from conftest import skill_dir
from mdf_test_support import git, init_git, mdf, payload


BEGIN = "<!-- MDF:BEGIN -->"


END = "<!-- MDF:END -->"


def write_agents_template(skill: Path, body: str) -> None:
    folder = skill / "assets" / "templates"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "agents-managed-block.md").write_text(
        f"{BEGIN}\n{body}\n{END}\n", encoding="utf-8"
    )


def init_upstream(
    tmp_path: Path, marker: str, *, agents_body: str | None = None
) -> Path:
    source = tmp_path / "upstream"
    skill = source / "skills" / "mdf"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"{marker}\n", encoding="utf-8")
    (skill / "references" / "note.md").write_text("skill\n", encoding="utf-8")
    if agents_body is not None:
        write_agents_template(skill, agents_body)
    init_git(source)
    return source


def write_installed(repo: Path, folder: str, marker: str, version: str) -> Path:
    skill = repo / folder / "mdf"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"{marker}\n", encoding="utf-8")
    (skill / "references" / ".version").write_text(
        f"{version}\n", encoding="utf-8"
    )
    return skill


def init_target(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("app\n", encoding="utf-8")
    (target / "docs").mkdir()
    (target / "docs" / "README.md").write_text("keep-docs\n", encoding="utf-8")
    (target / ".mdf").mkdir()
    (target / ".mdf" / "manifest.yaml").write_text(
        "# keep-mdf\n", encoding="utf-8"
    )
    (target / "skills" / "mdf").mkdir(parents=True)
    (target / "skills" / "mdf" / "SKILL.md").write_text(
        "source-tree\n", encoding="utf-8"
    )
    write_installed(target, ".codex/skills", "old-codex", "old-codex-hash")
    write_installed(target, ".cursor/skills", "old-cursor", "old-cursor-hash")
    init_git(target)
    return target


def source_head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").stdout.strip()
