"""release-closeout 的输入校验、hotfix 身份、证据聚合与重复组归档。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_removed_verify_command_argument_is_a_hard_failure(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = mdf(
        python_exe,
        "release-closeout",
        "--repo",
        str(repo),
        "--verify-command",
        "true",
    )
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr


DUPLICATE_ID = "bug-EF56"


DUPLICATE_NAME = f"{DUPLICATE_ID}-duplicate.md"


def closeout_args(repo: Path, *extra: str) -> list[str]:
    return closeout_cli_args(  # noqa: F405
        "release-closeout",
        "--repo",
        str(repo),
        "--release-date",
        "2026-07-30",
        *extra,
    )


def prepare_release(repo: Path, slug: str = "service-health") -> None:
    replace(repo / "docs/bugs" / BUG_NAME, "status: open", "status: fixed")
    init_git(repo)  # noqa: F405
    write_unreleased_change(repo, slug)  # noqa: F405
    git(repo, "add", "--all")  # noqa: F405
    git(repo, "commit", "-m", "test: 准备发布")  # noqa: F405
    git(repo, "checkout", "-b", "release/1.3.0")  # noqa: F405


def write_closed_duplicate(repo: Path) -> None:
    duplicate = repo / "docs/bugs" / DUPLICATE_NAME
    duplicate.write_text(
        (
            "---\n"
            f"id: {DUPLICATE_ID}\n"
            "type: bug\n"
            "status: rejected\n"
            "reject-reason: duplicate\n"
            f"duplicate_of: {BUG_ID}\n"  # noqa: F405
            "---\n\n"
            "# Duplicate\n\n"
            "## 观察到的行为\n\n相同。\n\n"
            "## 期望行为\n\n相同。\n\n"
            "## 复现步骤\n\n相同。\n\n"
            "## 影响\n\n无。\n\n"
            "## 所需回归证据\n\n无。\n"
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(  # noqa: F405
    ("outcome", "expected_archive"),
    [
        ("fixed", True),
        ("closed", True),
        ("deferred", False),
    ],
)
def test_release_closeout_handles_quoted_object_values_end_to_end(
    python_exe: str,
    tmp_path: Path,
    outcome: str,
    expected_archive: bool,
):
    repo = copy_fixture(tmp_path)  # noqa: F405
    bug = repo / "docs/bugs" / BUG_NAME  # noqa: F405
    replace(bug, "status: open", 'status: "fixed" # pending verification')  # noqa: F405
    replace(  # noqa: F405
        bug,
        "found_in: unreleased",
        "found_in: 'unreleased' # current line",
    )
    if outcome != "fixed":
        replace(bug, "severity: major", "severity: trivial")  # noqa: F405
    init_git(repo)  # noqa: F405
    write_unreleased_change(repo, "quoted-object")  # noqa: F405
    change = repo / "changes" / "unreleased" / "quoted-object" / "CHANGE.md"
    if outcome == "closed":
        replace(  # noqa: F405
            bug,
            'status: "fixed" # pending verification',
            'status: "rejected" # terminal\nreject-reason: wont-fix',
        )
        replace(change, f"fixed: [{BUG_ID}]", "fixed: []")  # noqa: F405
        replace(change, "closed: []", f"closed: [{BUG_ID}]")  # noqa: F405
    elif outcome == "deferred":
        replace(  # noqa: F405
            bug,
            'status: "fixed" # pending verification',
            'status: "open" # still active',
        )
        replace(change, f"fixed: [{BUG_ID}]", "fixed: []")  # noqa: F405
        replace(change, "deferred: []", f"deferred: [{BUG_ID}]")  # noqa: F405
    git(repo, "add", "--all")  # noqa: F405
    git(repo, "commit", "-m", "test: 引号与注释对象")  # noqa: F405
    git(repo, "checkout", "-b", "release/1.3.0")  # noqa: F405
    seed_verify_full(python_exe, repo)  # noqa: F405

    payload(mdf(python_exe, *closeout_args(repo)))  # noqa: F405

    if expected_archive:
        result = repo / "docs/bugs" / "archive" / "1.3" / BUG_NAME  # noqa: F405
        expected_status = "rejected" if outcome == "closed" else "closed"
        assert f'status: "{expected_status}"' in result.read_text(
            encoding="utf-8"
        ) or f"status: {expected_status}" in result.read_text(encoding="utf-8")
    else:
        result = bug
        assert 'status: "open" # still active' in result.read_text(encoding="utf-8")
    text = result.read_text(encoding="utf-8")
    assert "found_in: 1.3.0" in text
    assert "unreleased" not in text


def test_change_evidence_requires_non_empty_string_elements(
    python_exe: str,
    tmp_path: Path,
):
    repo = copy_fixture(tmp_path)  # noqa: F405
    write_unreleased_change(repo, "service-health")  # noqa: F405
    change = repo / "changes" / "unreleased" / "service-health" / "CHANGE.md"
    replace(  # noqa: F405
        change,
        "  tests: [tests/test_service.py]",
        '  tests: [""]',
    )
    init_git(repo)  # noqa: F405

    result = mdf(python_exe, "validate", "--repo", str(repo))  # noqa: F405

    assert result.returncode != 0
    assert "change.evidence" in result.stdout


def test_closeout_requires_an_explicit_release_date(
    python_exe: str,
    tmp_path: Path,
):
    repo = copy_fixture(tmp_path)  # noqa: F405
    prepare_release(repo)
    arguments = closeout_cli_args(  # noqa: F405
        "release-closeout",
        "--repo",
        str(repo),
    )

    result = mdf(python_exe, *arguments, "--dry-run")  # noqa: F405

    assert result.returncode != 0
    assert "invalid_closeout_spec" in result.stderr


def test_hotfix_rejects_missing_empty_and_unknown_input(
    python_exe: str,
    tmp_path: Path,
):
    invalid_inputs = [
        None,
        "{}",
        json.dumps(
            {
                "body": " ",
                "release_notes": {"Fixed": ["修复"]},
                "evidence": {
                    "tests": [],
                    "commands": ["true"],
                    "artifacts": [],
                },
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "body": "修复。",
                "release_notes": {"Fixed": ["修复"]},
                "evidence": {"tests": [], "commands": [], "artifacts": []},
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "body": "修复。",
                "release_notes": {"Fixed": ["修复"]},
                "evidence": {
                    "tests": [],
                    "commands": ["true"],
                    "artifacts": [],
                },
                "change_kind": "release",
                "source_branch": "hotfix/1.2.1",
                "unknown": True,
            },
            ensure_ascii=False,
        ),
    ]
    for raw in invalid_inputs:
        repo = copy_fixture(tmp_path / str(len(str(raw))))  # noqa: F405
        init_git(repo)  # noqa: F405
        git(repo, "checkout", "-b", "hotfix/1.2.1")  # noqa: F405
        args = closeout_args(repo)
        if raw is not None:
            args.extend(["--hotfix-change-json", raw])

        result = mdf(python_exe, *args, "--dry-run")  # noqa: F405

        assert result.returncode != 0
        assert "invalid_closeout_spec" in result.stderr


def test_hotfix_injects_identity_and_aggregates_evidence_in_order(
    python_exe: str,
    tmp_path: Path,
):
    repo = copy_fixture(tmp_path)  # noqa: F405
    replace(repo / "docs/bugs" / BUG_NAME, "status: open", "status: fixed")  # noqa: F405
    init_git(repo)  # noqa: F405
    git(repo, "checkout", "-b", "hotfix/1.2.1")  # noqa: F405
    seed_verify_full(python_exe, repo)  # noqa: F405
    hotfix = json.dumps(
        {
            "body": "调用超时已经修复。",
            "fixed": [BUG_ID],  # noqa: F405
            "release_notes": {"Fixed": ["修复调用超时"]},
            "evidence": {
                "tests": ["tests/test_timeout.py"],
                "commands": ["check-timeout", "true", "check-timeout"],
                "artifacts": ["artifacts/timeout.txt"],
            },
        },
        ensure_ascii=False,
    )

    payload(
        mdf(python_exe, *closeout_args(repo, "--hotfix-change-json", hotfix))
    )  # noqa: F405
    root = (repo / "changes" / "1.2.1" / "CHANGE.md").read_text(
        encoding="utf-8"
    )

    assert "change_kind: hotfix" in root
    assert "source_branch: hotfix/1.2.1" in root
    assert root.index('"check-timeout"') < root.index('"true"')
    assert root.count('"check-timeout"') == 1
    assert '"tests/test_timeout.py"' in root
    assert '"artifacts/timeout.txt"' in root


def test_release_aggregates_child_evidence_before_manifest_commands(
    python_exe: str,
    tmp_path: Path,
):
    repo = copy_fixture(tmp_path)  # noqa: F405
    replace(repo / "docs/bugs" / BUG_NAME, "status: open", "status: fixed")  # noqa: F405
    init_git(repo)  # noqa: F405
    write_unreleased_change(repo, "alpha")  # noqa: F405
    write_unreleased_change(repo, "zeta")  # noqa: F405
    zeta = repo / "changes" / "unreleased" / "zeta" / "CHANGE.md"
    replace(  # noqa: F405
        zeta,
        "  tests: [tests/test_service.py]",
        "  tests: [tests/test_service.py, tests/test_extra.py]",
    )
    replace(  # noqa: F405
        zeta,
        '  commands: ["python -m pytest"]',
        '  commands: ["python -m pytest", "python -m mypy"]',
    )
    replace(  # noqa: F405
        zeta,
        "  artifacts: []",
        "  artifacts: [dist/report.json]",
    )
    git(repo, "add", "--all")  # noqa: F405
    git(repo, "commit", "-m", "test: 两个 Change 证据")  # noqa: F405
    git(repo, "checkout", "-b", "release/1.3.0")  # noqa: F405
    seed_verify_full(python_exe, repo)  # noqa: F405

    payload(mdf(python_exe, *closeout_args(repo)))  # noqa: F405
    root = (repo / "changes" / "1.3.0" / "CHANGE.md").read_text(
        encoding="utf-8"
    )

    assert root.index('"tests/test_service.py"') < root.index(
        '"tests/test_extra.py"'
    )
    assert root.index('"python -m pytest"') < root.index('"python -m mypy"')
    assert root.index('"python -m mypy"') < root.index('"true"')
    assert root.count('"python -m pytest"') == 1
    assert '"dist/report.json"' in root


def test_duplicate_can_close_before_canonical_but_manual_archive_rejects(
    python_exe: str,
    tmp_path: Path,
):
    repo = copy_fixture(tmp_path)  # noqa: F405
    write_closed_duplicate(repo)
    init_git(repo)  # noqa: F405

    assert_ok(
        mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    )  # noqa: F405
    result = mdf(  # noqa: F405
        python_exe,
        "archive",
        "--repo",
        str(repo),
        "--epoch",
        "1.3",
        "--dry-run",
    )

    assert result.returncode != 0
    assert "duplicate_group_open" in result.stderr


def test_release_closeout_archives_the_whole_duplicate_group(
    python_exe: str,
    tmp_path: Path,
):
    repo = copy_fixture(tmp_path)  # noqa: F405
    write_closed_duplicate(repo)
    prepare_release(repo)
    seed_verify_full(python_exe, repo)  # noqa: F405

    payload(mdf(python_exe, *closeout_args(repo)))  # noqa: F405

    archive = repo / "docs/bugs" / "archive" / "1.3"
    assert (archive / BUG_NAME).is_file()  # noqa: F405
    assert (archive / DUPLICATE_NAME).is_file()
