"""detach 只删除仓内 Skill 副本。"""
from __future__ import annotations

from pathlib import Path

import pytest

from mdf_core.workspace.detach import _allowed
from mdf_test_support import git, init_git, mdf, payload


def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    skill = repo / ".codex" / "skills" / "mdf"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("vendored\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "README.md").write_text("keep-docs\n", encoding="utf-8")
    (repo / ".mdf").mkdir()
    (repo / ".mdf" / "manifest.yaml").write_text("schema_version: 3\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text(
        "keep\n<!-- MDF:BEGIN -->\nold\n<!-- MDF:END -->\n", encoding="utf-8",
    )
    init_git(repo)
    return repo


@pytest.mark.parametrize("track_entry", [True, False])
def test_detach_removes_only_the_skill_copy(python_exe: str, tmp_path: Path, track_entry: bool) -> None:
    repo = repository(tmp_path)
    entry = repo / ".agents/skills/mdf"
    (entry / "agents").mkdir(parents=True)
    names = ("SKILL.md", "agents/openai.yaml", "mdf_entry.py")
    for name in names:
        (entry / name).write_text(f"thin entry {name}\n", encoding="utf-8")
    if track_entry:
        git(repo, "add", "--", str(entry.relative_to(repo)))
        git(repo, "commit", "-m", "test: 跟踪项目引导")
    tracked = git(repo, "ls-files", "--stage", "--", str(entry.relative_to(repo))).stdout
    data = payload(mdf(python_exe, "detach", "--repo", str(repo)))
    assert data["action"] == "created"
    assert not (repo / ".codex" / "skills" / "mdf").exists()
    assert (repo / "docs" / "README.md").read_text(encoding="utf-8") == "keep-docs\n"
    assert (repo / ".mdf" / "manifest.yaml").is_file()
    assert git(repo, "ls-files", "--stage", "--", str(entry.relative_to(repo))).stdout == tracked
    assert all((entry / name).read_text(encoding="utf-8") == f"thin entry {name}\n" for name in names)
    assert "keep\n" in (repo / "AGENTS.md").read_text(encoding="utf-8")
    message = git(repo, "log", "-1", "--format=%s").stdout.strip()
    assert message == "chore(mdf): 移除仓内 MDF Skill 副本"
    again = payload(mdf(python_exe, "detach", "--repo", str(repo)))
    assert again["action"] == "none"


def test_detach_refuses_a_dirty_copy(python_exe: str, tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / ".codex" / "skills" / "mdf" / "SKILL.md").write_text("dirty\n", encoding="utf-8")
    result = mdf(python_exe, "detach", "--repo", str(repo))
    assert result.returncode != 0
    assert "detach_dirty" in result.stderr
    assert (repo / ".codex" / "skills" / "mdf" / "SKILL.md").is_file()
    assert (repo / "docs" / "README.md").is_file()


def test_detach_paths_cannot_escape() -> None:
    assert _allowed(".codex/skills/mdf")
    assert _allowed(".codex/skills/mdf/SKILL.md")
    assert not _allowed(".mdf/manifest.yaml")
    assert not _allowed("docs/README.md")
    assert not _allowed("../.codex/skills/mdf")
    assert not _allowed(".codex/skills/other")
