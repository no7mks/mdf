"""仓库根 .gitignore 的补齐是纯文本变换，不重排已有规则。"""
from __future__ import annotations

from pathlib import Path

import pytest

from mdf_core.foundation.constants import BASELINES
from mdf_core.foundation.errors import MDFError
from mdf_core.workspace.init_repo import init_files
from mdf_home import HomeError, _upgrade_repo, ensure_project_gitignore, project_gitignore_text
from mdf_test_support import git, init_git

BLOCK = (
    "# MDF local artifacts\n"
    "/.mdf/logs/\n"
    "/.mdf/tmp/\n"
    "/.mdf/reports/\n"
    "/.mdf/cache/\n"
)


def test_empty_text_gets_the_block() -> None:
    assert project_gitignore_text("") == BLOCK


def test_complete_text_is_unchanged() -> None:
    text = "keep\n" + BLOCK + "tail\n"
    assert project_gitignore_text(text) == text
    assert project_gitignore_text(project_gitignore_text(text)) == text


def test_partial_keeps_the_existing_line_in_place() -> None:
    text = "node_modules/\n/.mdf/tmp/\n"
    result = project_gitignore_text(text)
    assert result.startswith("node_modules/\n/.mdf/tmp/\n\n# MDF local artifacts\n")
    assert result.count("/.mdf/tmp/") == 1
    assert "/.mdf/logs/\n" in result
    assert project_gitignore_text(result) == result


def test_header_inserts_missing_lines_at_the_segment_end() -> None:
    text = "# MDF local artifacts\n/.mdf/logs/\n\nkeep\n"
    assert project_gitignore_text(text) == (
        "# MDF local artifacts\n"
        "/.mdf/logs/\n"
        "/.mdf/tmp/\n"
        "/.mdf/reports/\n"
        "/.mdf/cache/\n"
        "\nkeep\n"
    )


def test_unanchored_pattern_is_not_treated_as_present() -> None:
    result = project_gitignore_text(".mdf/tmp/\n")
    assert result.startswith(".mdf/tmp/\n\n# MDF local artifacts\n")
    assert "/.mdf/tmp/\n" in result


def test_removes_entry_ignore_with_all_local_rules_present() -> None:
    text = BLOCK + "/.agents/skills/mdf/\n/.agents/skills/other/\n"
    expected = BLOCK + "/.agents/skills/other/\n"
    assert project_gitignore_text(text) == expected
    assert project_gitignore_text(expected) == expected


def test_ensure_rejects_a_symlink_without_following_it(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("x\n", encoding="utf-8")
    (repo / ".gitignore").symlink_to(outside)
    with pytest.raises(HomeError) as info:
        ensure_project_gitignore(repo)
    assert info.value.code == "managed_symlink"
    assert outside.read_text(encoding="utf-8") == "x\n"


def test_init_files_rejects_a_gitignore_symlink(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".mdf").mkdir()
    outside = tmp_path / "outside"
    outside.write_text("x\n", encoding="utf-8")
    (repo / ".gitignore").symlink_to(outside)
    baselines = {
        name: {"status": "not_applicable", "reason": "测试"} for name in BASELINES
    }
    with pytest.raises(MDFError) as info:
        init_files(
            repo, baselines, latest_release=None,
            verification={
                name: "true"
                for name in ("lint", "build", "quick", "smoke", "release")
            },
            implementation_roots=["src"],
        )
    assert info.value.code == "managed_symlink"
    assert outside.read_text(encoding="utf-8") == "x\n"


def _mdf_repo(path: Path) -> Path:
    path.mkdir()
    (path / ".mdf").mkdir()
    (path / ".mdf" / "manifest.yaml").write_text("schema_version: 3\n", encoding="utf-8")
    (path / "README.md").write_text("repo\n", encoding="utf-8")
    init_git(path)
    return path


def test_explicit_repo_must_be_the_git_root(tmp_path: Path, monkeypatch) -> None:
    repo = _mdf_repo(tmp_path / "repo")
    nested = repo / "src"
    nested.mkdir()
    with pytest.raises(HomeError) as info:
        _upgrade_repo(str(nested))
    assert info.value.code == "upgrade_repo_invalid"
    monkeypatch.chdir(nested)
    assert _upgrade_repo(None) == repo.resolve()


def test_explicit_repo_expands_home_and_accepts_worktrees_and_plain_directories(tmp_path: Path, monkeypatch) -> None:
    repo = _mdf_repo(tmp_path / "repo")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert _upgrade_repo("~/repo") == repo.resolve()
    plain = tmp_path / "plain"
    plain.mkdir()
    assert _upgrade_repo(str(plain)) == plain.resolve()
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "--detach", str(linked))
    assert _upgrade_repo(str(linked)) == linked.resolve()


def test_explicit_repo_rejects_git_directories_without_a_worktree(tmp_path: Path) -> None:
    repo = _mdf_repo(tmp_path / "repo")
    bare = tmp_path / "bare.git"
    git(tmp_path, "init", "--bare", str(bare))
    for directory in (repo / ".git", bare):
        with pytest.raises(HomeError) as info:
            _upgrade_repo(str(directory))
        assert info.value.code == "upgrade_repo_invalid"
