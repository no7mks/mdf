"""Mars Development Flow 归档、写入与 worktree 纪律测试。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403


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


def test_archive_post_validation_failure_leaves_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    core = load_core_module()
    repo = copy_fixture(tmp_path)
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "status: ready\ndepends_on: []",
        (
            "status: released\ndepends_on: []\n"
            ""
            "released_in: 1.2.0"
        ),
    )
    init_git(repo)

    calls = {"n": 0}

    def fake_findings(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return []
        return [
            core.Finding("injected.failure", "forced post-validation failure")
        ]

    monkeypatch.setattr("mdf_core.doctor.collect_findings", fake_findings)
    args = SimpleNamespace(repo=str(repo), epoch="1.2", dry_run=False)
    with pytest.raises(core.MDFError) as caught:
        core.command_archive(args)
    assert caught.value.code == "post_validation_failed"
    assert not (repo / "docs/proposals" / PRP_NAME).exists()
    assert (repo / "docs/proposals" / "archive" / "1.2" / PRP_NAME).is_file()
    assert git(repo, "status", "--porcelain").stdout


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


def test_move_rewrite_failure_leaves_partial_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    core = load_core_module()
    repo = tmp_path / "repo"
    source = repo / "docs/proposals" / "record"
    source.mkdir(parents=True)
    (source / "item.md").write_text("# Item\n", encoding="utf-8")
    reference = repo / "reference.md"
    reference.write_text(
        "[Item](docs/proposals/record/item.md)\n", encoding="utf-8"
    )
    destination = repo / "docs/proposals" / "archive" / "1.0" / "record"
    moves = {source: destination}
    rewrites = core.replacement_plan(repo, moves)

    original_write = Path.write_text

    def fail_reference(path, *args, **kwargs):
        if path == reference:
            raise OSError("injected rewrite failure")
        return original_write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_reference)
    with pytest.raises(OSError, match="injected rewrite failure"):
        core.apply_moves_and_rewrites(moves, rewrites)

    assert not source.exists()
    assert (destination / "item.md").is_file()
    assert reference.read_text(encoding="utf-8") == (
        "[Item](docs/proposals/record/item.md)\n"
    )
    assert (repo / "docs/proposals" / "archive").is_dir()


def test_init_refuses_to_overwrite_unexpected_files(tmp_path: Path):
    core = load_core_module()
    existing = tmp_path / "docs" / "README.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("keep me\n", encoding="utf-8")

    with pytest.raises(core.MDFError) as caught:
        core.write_files({existing: "overwritten\n"})
    assert caught.value.code == "init_collision"
    assert existing.read_text(encoding="utf-8") == "keep me\n"


def test_init_write_failure_leaves_partial_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    core = load_core_module()
    replaced_existing = tmp_path / "CHANGELOG.md"
    replaced_existing.write_text("original changelog\n", encoding="utf-8")
    created = tmp_path / "docs" / "README.md"
    blocked = tmp_path / "AGENTS.md"
    files = {
        replaced_existing: "updated changelog\n",
        created: "# Docs\n",
        blocked: "# Agents\n",
    }
    original_write = Path.write_text

    def fail_on_blocked(path, *args, **kwargs):
        if path == blocked:
            raise OSError("injected write failure")
        return original_write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_on_blocked)
    with pytest.raises(OSError, match="injected write failure"):
        core.write_files(files, replace_allowed={replaced_existing})

    assert (
        replaced_existing.read_text(encoding="utf-8") == "updated changelog\n"
    )
    assert created.read_text(encoding="utf-8") == "# Docs\n"
    assert not blocked.exists()


def test_init_allows_dirty_worktree_for_active_continuation(
    python_exe: str, tmp_path: Path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Test\n", encoding="utf-8")
    init_git(repo)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    arguments = [
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "none",
        *all_not_applicable_baselines(),
        "--verification-item",
        '{"id": "check", "kind": "custom", "command": "true"}',
    ]

    applied = payload(mdf(python_exe, *arguments))
    assert applied["operation"] == "init"
    assert (repo / ".mdf" / "manifest.yaml").is_file()
    assert (repo / "docs/JOTS.md").read_text(encoding="utf-8") == "# 随手记录\n"


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
