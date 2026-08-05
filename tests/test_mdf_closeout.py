"""MDF release-closeout 协议测试。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403


def release_arguments(repo: Path, **extra: str) -> list[str]:
    args = [
        "release-closeout",
        "--repo",
        str(repo),
        "--release-date",
        "2026-07-30",
    ]
    for key, value in extra.items():
        args.extend([f"--{key.replace('_', '-')}", value])
    return closeout_cli_args(*args)


def prepare_release(repo: Path, slug: str = "service-health") -> None:
    init_git(repo)
    write_unreleased_change(repo, slug)
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 准备发布变更")
    git(repo, "checkout", "-b", "release/1.3.0")


def test_closeout_preview_is_optional_read_only_summary_then_apply(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    prepare_release(repo)
    arguments = release_arguments(repo)

    preview = payload(mdf(python_exe, *arguments, "--dry-run"))
    summary = preview["summary"]
    assert preview["dry_run"] is True
    assert summary["version"] == "1.3.0"
    assert summary["outcomes"]
    assert summary["moves"]
    assert summary["affected_files"]
    assert summary["verification"] == {"commands": ["true"], "executed": False}
    assert "confirmation_required" not in preview
    assert "digest" not in json.dumps(preview)
    assert "writes" not in summary
    assert not (repo / "changes" / "1.3.0").exists()
    assert not git(repo, "status", "--porcelain").stdout

    applied = payload(mdf(python_exe, *arguments))
    assert applied["dry_run"] is False
    assert applied["verification"]["results"] == [
        {"command": "true", "exit_code": 0}
    ]
    release_dir = repo / "changes" / "1.3.0"
    assert (release_dir / "CHANGE.md").is_file()
    assert (release_dir / "service-health" / "CHANGE.md").is_file()
    assert (repo / "proposals" / "archive" / "1.3" / PRP_NAME).is_file()
    assert (repo / "bugs" / "archive" / "1.3" / BUG_NAME).is_file()
    assert "- Semantic summary: semantic audit completed in test" in (
        release_dir / "CHANGE.md"
    ).read_text(encoding="utf-8")
    assert_ok(
        mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    )


def test_closeout_preview_requires_semantic_attestation(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    prepare_release(repo)

    result = mdf(
        python_exe,
        "release-closeout",
        "--repo",
        str(repo),
        "--release-date",
        "2026-07-30",
        "--dry-run",
    )
    assert result.returncode != 0
    assert "invalid_closeout_spec" in result.stderr


def test_closeout_rejects_missing_or_blank_semantic_summary(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    prepare_release(repo)

    for attestation in (
        json.dumps({"semantic": "passed", "finding_count": 0}),
        semantic_attestation_json(summary="   "),
    ):
        result = mdf(
            python_exe,
            "release-closeout",
            "--repo",
            str(repo),
            "--release-date",
            "2026-07-30",
            "--dry-run",
            "--semantic-attestation-json",
            attestation,
        )
        assert result.returncode != 0
        assert "invalid_closeout_spec" in result.stderr


def test_closeout_uses_manifest_commands_and_stops_if_they_dirty_repo(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / ".mdf" / "manifest.yaml",
        '- "true"',
        '- "touch verification-marker"',
    )
    prepare_release(repo)
    arguments = release_arguments(repo)

    preview = payload(mdf(python_exe, *arguments, "--dry-run"))
    assert preview["summary"]["verification"]["executed"] is False
    assert not (repo / "verification-marker").exists()

    result = mdf(python_exe, *arguments)
    assert result.returncode != 0
    assert "dirty_worktree" in result.stderr
    assert (repo / "verification-marker").is_file()
    assert not (repo / "changes" / "1.3.0").exists()


def test_closeout_rejects_unclassified_unreleased_bug_on_apply(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    write_unreleased_change(repo, "service-health")
    replace(
        repo / "changes" / "unreleased" / "service-health" / "CHANGE.md",
        f"fixed: [{BUG_ID}]",
        "fixed: []",
    )
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 遗漏未发布 Bug")
    git(repo, "checkout", "-b", "release/1.3.0")

    result = mdf(python_exe, *release_arguments(repo))
    assert result.returncode != 0
    assert "unclassified_unreleased_bug" in result.stderr
    assert not (repo / "changes" / "1.3.0").exists()


def test_critical_bug_cannot_be_wont_fixed_at_closeout(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(repo / "bugs" / BUG_NAME, "severity: major", "severity: critical")
    init_git(repo)
    write_unreleased_change(repo, "timeout-close")
    change = repo / "changes" / "unreleased" / "timeout-close" / "CHANGE.md"
    replace(change, f"fixed: [{BUG_ID}]", "fixed: []")
    replace(change, "closed: []", f"closed: [{BUG_ID}]")
    replace(
        change,
        "closed_resolutions: {}",
        f"closed_resolutions:\n  {BUG_ID}: wont-fix",
    )
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: critical wont-fix")
    git(repo, "checkout", "-b", "release/1.3.0")

    result = mdf(python_exe, *release_arguments(repo))
    assert result.returncode != 0
    assert "critical_bug_blocks_release" in result.stderr


def prepare_wont_fix_release(repo: Path) -> None:
    init_git(repo)
    write_unreleased_change(repo, "service-health")
    change = repo / "changes" / "unreleased" / "service-health" / "CHANGE.md"
    replace(change, f"fixed: [{BUG_ID}]", "fixed: []")
    replace(change, "closed: []", f"closed: [{BUG_ID}]")
    replace(
        change,
        "closed_resolutions: {}",
        f"closed_resolutions:\n  {BUG_ID}: wont-fix",
    )
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: major wont-fix")
    git(repo, "checkout", "-b", "release/1.3.0")


def test_major_bug_wont_fix_needs_explicit_acceptance(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    prepare_wont_fix_release(repo)

    rejected = mdf(python_exe, *release_arguments(repo))
    assert rejected.returncode != 0
    assert "severity_gate" in rejected.stderr

    acceptance = json.dumps(
        {
            BUG_ID: {
                "accepted": True,
                "reason": "极端场景影响可接受",
                "follow_up": "下个 minor 处理",
            }
        },
        ensure_ascii=False,
    )
    accepted_root = tmp_path / "accepted"
    accepted_root.mkdir()
    accepted_repo = copy_fixture(accepted_root)
    prepare_wont_fix_release(accepted_repo)
    applied = payload(
        mdf(
            python_exe,
            *release_arguments(
                accepted_repo, deferred_acceptance_json=acceptance
            ),
        )
    )
    assert applied["outcomes"]["closed"] == [BUG_ID]
    archived = accepted_repo / "bugs" / "archive" / "1.3" / BUG_NAME
    assert archived.is_file()
    assert "resolution: wont-fix" in archived.read_text(encoding="utf-8")


def test_hotfix_closeout_uses_manifest_commands(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "checkout", "-b", "hotfix/1.2.1")
    hotfix = json.dumps(
        {
            "fixed": [BUG_ID],
            "release_notes": {"Fixed": ["修复调用超时"]},
            "body": "调用超时已经修复。",
            "evidence": {
                "tests": ["tests/test_timeout.py"],
                "commands": ["python -m pytest tests/test_timeout.py"],
                "artifacts": [],
            },
        },
        ensure_ascii=False,
    )

    applied = payload(
        mdf(
            python_exe,
            *release_arguments(repo, hotfix_change_json=hotfix),
        )
    )
    assert applied["version"] == "1.2.1"
    assert (repo / "changes" / "1.2.1" / "CHANGE.md").is_file()
    assert (repo / "bugs" / "archive" / "1.2" / BUG_NAME).is_file()


def test_closeout_requires_clean_worktree_for_preview_and_apply(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    prepare_release(repo)
    (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    for suffix in ([], ["--dry-run"]):
        result = mdf(python_exe, *release_arguments(repo), *suffix)
        assert result.returncode != 0
        assert "dirty_worktree" in result.stderr
