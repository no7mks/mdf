"""archive 的预览、移动、链接重写与前置条件。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
import re
import shlex
import unicodedata
from conftest import skill_dir


def test_archive_accepts_closed_non_delivery_resolution(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    proposal = repo / "docs/proposals" / PRP_NAME
    replace(
        proposal,
        "status: ready\ndepends_on: []",
        "status: rejected\ndepends_on: []\nreject-reason: wont-do",
    )
    init_git(repo)

    arguments = [
        "archive",
        "--repo",
        str(repo),
        "--epoch",
        "2.0",
    ]
    dry_run = payload(mdf(python_exe, *arguments, "--dry-run"))
    assert "plan_digest" not in dry_run
    assert_ok(mdf(python_exe, *arguments))
    assert (repo / "docs/proposals" / "archive" / "2.0" / PRP_NAME).is_file()


def test_duplicate_group_archives_primary_and_child_together(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    primary = repo / "docs/bugs" / BUG_NAME
    replace(
        primary,
        "status: open",
        "status: rejected\nreject-reason: wont-fix",
    )
    replace(primary, "found_in: unreleased", "found_in: 1.2.0")
    duplicate_name = "bug-EF56-duplicate.md"
    (repo / "docs/bugs" / duplicate_name).write_text(
        "---\n"
        "id: bug-EF56\n"
        "type: bug\n"
        "status: rejected\n"
        "reject-reason: duplicate\n"
        f"duplicate_of: {BUG_ID}\n"
        "---\n\n"
        "# Duplicate\n\n"
        "## 观察到的行为\n\n相同。\n\n"
        "## 期望行为\n\n相同。\n\n"
        "## 复现步骤\n\n相同。\n\n"
        "## 影响\n\n无。\n\n"
        "## 所需回归证据\n\n无。\n",
        encoding="utf-8",
    )
    init_git(repo)
    dry_run = payload(
        mdf(
            python_exe,
            "archive",
            "--repo",
            str(repo),
            "--epoch",
            "1.3",
            "--dry-run",
        )
    )
    moved = {(item["from"], item["to"]) for item in dry_run["moves"]}
    assert any(
        duplicate_name in source and "archive/1.3" in target
        for source, target in moved
    )
    assert any(
        BUG_NAME in source and "archive/1.3" in target
        for source, target in moved
    )


def test_archive_requires_clean_worktree(
    python_exe: str, tmp_path: Path
):
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    archive_repo = copy_fixture(archive_root)
    proposal = archive_repo / "docs/proposals" / PRP_NAME
    replace(
        proposal,
        "status: ready\ndepends_on: []",
        "status: rejected\ndepends_on: []\nreject-reason: wont-do",
    )
    init_git(archive_repo)
    (archive_repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    for suffix in ([], ["--dry-run"]):
        result = mdf(
            python_exe,
            "archive",
            "--repo",
            str(archive_repo),
            "--epoch",
            "1.2",
            *suffix,
        )
        assert result.returncode != 0
        assert "dirty_worktree" in result.stderr


def test_archive_dry_run_then_moves_closed_item_and_rewrites_links(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    proposal = repo / "docs/proposals" / PRP_NAME
    replace(
        proposal,
        "status: ready\ndepends_on: []",
        (
            "status: released\ndepends_on: []\n"
            ""
            "released_in: 1.2.0"
        ),
    )
    proposal.write_text(
        proposal.read_text(encoding="utf-8")
        + f'\n[Known bug](../bugs/{BUG_NAME}#impact "Regression context")\n',
        encoding="utf-8",
    )
    init_git(repo)

    dry_run = mdf(
        python_exe,
        "archive",
        "--repo",
        str(repo),
        "--epoch",
        "1.2",
        "--dry-run",
    )
    assert_ok(dry_run)
    assert PRP_NAME in dry_run.stdout
    assert "plan_digest" not in json.loads(dry_run.stdout)
    assert proposal.is_file(), "dry-run 不得移动文件"
    assert not (repo / "docs/proposals" / "archive" / "1.2" / PRP_NAME).exists()
    assert not git(repo, "status", "--porcelain").stdout

    applied = mdf(
        python_exe,
        "archive",
        "--repo",
        str(repo),
        "--epoch",
        "1.2",
    )
    assert_ok(applied)
    archived = repo / "docs/proposals" / "archive" / "1.2" / PRP_NAME
    assert archived.is_file()
    assert not proposal.exists()
    archived_text = archived.read_text(encoding="utf-8")
    assert f'[Known bug](../../../bugs/{BUG_NAME}#impact "Regression context")' in archived_text

    reference = (
        repo / "docs" / "user-guide" / "README.md"
    ).read_text(encoding="utf-8")
    assert f"../proposals/archive/1.2/{PRP_NAME}" in reference
    assert f"../proposals/{PRP_NAME}" not in reference


def test_archive_never_rewrites_external_url_path_text(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    proposal = repo / "docs/proposals" / PRP_NAME
    replace(
        proposal,
        "status: ready\ndepends_on: []",
        "status: rejected\ndepends_on: []\nreject-reason: wont-do",
    )
    external_url = f"https://example.invalid/repository/proposals/{PRP_NAME}"
    index = repo / "docs" / "README.md"
    index.write_text(
        index.read_text(encoding="utf-8")
        + f"\n[External proposal]({external_url})\n",
        encoding="utf-8",
    )
    init_git(repo)
    arguments = [
        "archive",
        "--repo",
        str(repo),
        "--epoch",
        "1.2",
    ]

    plan = payload(mdf(python_exe, *arguments, "--dry-run"))
    assert "docs/README.md" not in plan["rewrites"]
    payload(mdf(python_exe, *arguments))
    assert external_url in index.read_text(encoding="utf-8")


def workflow(name: str) -> str:
    root = skill_dir("mdf")
    path = root / "SKILL.md" if name == "entry" else root / "references" / f"{name}.md"
    return path.read_text(encoding="utf-8")


def test_documented_archive_commands_work_from_outside_target(python_exe, tmp_path):
    from mdf_test_support import PRP_NAME, copy_fixture, git, init_git, mdf, payload, replace

    commands = re.findall(r'`(archive --repo [^`]+)`', workflow("archive"))
    assert len(commands) == 2
    repo = copy_fixture(tmp_path)
    proposal = repo / "docs/proposals" / PRP_NAME
    replace(proposal, "status: ready\ndepends_on: []",
            "status: rejected\ndepends_on: []\nreject-reason: wont-do")
    init_git(repo)
    for index, command in enumerate(commands):
        argv = [arg.replace("$REPO_ROOT", str(repo)).replace("$RELEASE_EPOCH", "1.2")
                for arg in shlex.split(command)]
        result = payload(mdf(python_exe, *argv, cwd=tmp_path))
        assert result["dry_run"] is (index == 0)
        assert result["validation"]["finding_count"] == 0
        if index == 0:
            assert proposal.is_file()
            assert not git(repo, "status", "--porcelain").stdout
        else:
            assert not proposal.exists()
            assert (repo / "docs/proposals" / "archive" / "1.2" / PRP_NAME).is_file()
