"""release-closeout 的预览、执行、验证命令与收口结果。"""
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
    replace(repo / "docs/bugs" / BUG_NAME, "status: open", "status: closed\nfixed_in: 1.3.0")
    init_git(repo, previous_release=True)
    write_unreleased_change(repo, slug)
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 准备发布变更")
    git(repo, "checkout", "-b", "release/1.3.0")


@pytest.mark.parametrize("artifact", [None, "logs", "reports", "tmp"])
def test_closeout_preview_is_optional_read_only_summary_then_apply(
    python_exe: str, tmp_path: Path, artifact
):
    repo = copy_fixture(tmp_path)
    if artifact:
        outside = tmp_path / "outside"
        outside.mkdir()
        (repo / ".mdf" / artifact).symlink_to(outside, target_is_directory=True)
    prepare_release(repo)
    arguments = release_arguments(repo)

    preview = payload(mdf(python_exe, *arguments, "--dry-run"))
    summary = preview["summary"]
    assert preview["dry_run"] is True
    assert summary["version"] == "1.3.0"
    assert summary["outcomes"]
    assert summary["moves"]
    assert summary["affected_files"]
    assert summary["verification"] == {
        "suites": ["quick", "release"],
        "commands": ["true", "true", SUITE_OK, SUITE_OK], "executed": False,
    }
    assert "confirmation_required" not in preview
    assert "digest" not in json.dumps(preview)
    assert "writes" not in summary
    assert not (repo / "changes" / "1.3.0").exists()
    assert not git(repo, "status", "--porcelain").stdout

    seed_verify_branch(python_exe, repo)
    applied = payload(mdf(python_exe, *arguments))
    assert applied["dry_run"] is False
    assert applied["verification"]["reused"] == (
        "changes/unreleased/1.3.0/verification-report.json"
    )
    results = applied["verification"]["results"]
    assert [(item["command"], item["exit_code"]) for item in results] == [
        ("true", 0), ("true", 0), (SUITE_OK, 0), (SUITE_OK, 0),
    ]
    assert results[0]["report"]["all_passed"] is True
    release_item = next(
        item for item in results if item.get("report", {}).get("suite") == "release"
    )
    assert release_item["report"]["tests"] == 1
    assert (repo / release_item["report"]["path"] / "summary.json").is_file()
    assert ".mdf/reports" not in git(repo, "status", "--porcelain", "--ignored=no").stdout
    release_dir = repo / "changes" / "1.3.0"
    assert (release_dir / "CHANGE.md").is_file()
    assert (release_dir / "service-health" / "CHANGE.md").is_file()
    assert (repo / "docs/proposals" / "archive" / "1.3" / PRP_NAME).is_file()
    assert (repo / "docs/bugs" / "archive" / "1.3" / BUG_NAME).is_file()
    assert "Semantic audit" not in (
        release_dir / "CHANGE.md"
    ).read_text(encoding="utf-8")
    assert_ok(
        mdf(python_exe, "validate", "--repo", str(repo), "--level", "strict")
    )


@pytest.mark.parametrize("changed_command", [False, True])
def test_closeout_preserves_failed_original_command_and_incremental_evidence(python_exe, tmp_path, changed_command):
    repo = copy_fixture(tmp_path)
    patch_module_command(repo, "release", lambda command: "printf release; " + command)
    prepare_release(repo)
    seed_verify_branch(python_exe, repo)
    path = repo / "changes/unreleased/1.3.0/verification-report.json"
    report = json.loads(path.read_text())
    item = report["results"][-1]
    item["exit_code"] = 1
    original = dict(item)
    original["passed"] = False
    if changed_command:
        patch_module_command(repo, "release", lambda command: "printf updated; " + command)
        item["command"] = "printf updated; " + item["command"]
    item["incremental"] = {
        "original": original,
        "reason": "仅失败 case 受修复影响",
        "runs": [{"command": "pytest tests/test_fixed.py", "exit_code": 0,
                  "report": ".mdf/reports/retry/junit.xml"}],
        "reused": [{"case": "tests/test_unchanged.py", "report": item["report"]["path"],
                    "reason": "未依赖修改的实现"}],
    }
    path.write_text(json.dumps(report))
    git(repo, "add", str(path), ".mdf/modules.yaml")
    git(repo, "commit", "-m", "test: 保存增量验证证据")

    applied = payload(mdf(python_exe, *release_arguments(repo)))
    retained = applied["verification"]["results"][-1]
    assert retained["incremental"] == item["incremental"]
    assert retained["exit_code"] == 1 and retained["passed"] is True
    change = (repo / "changes/1.3.0/CHANGE.md").read_text()
    assert f"`{item['command']}` → exit 0" not in change
    assert "增量汇总通过" in change
    assert '"exit_code": 1' in change
    assert "pytest tests/test_fixed.py" in change
    assert "tests/test_unchanged.py" in change
    assert item["report"]["path"] in change
    audit_json = change.split("    ```json\n", 1)[1].split("\n    ```", 1)[0]
    audit = json.loads(audit_json)
    assert audit["original_execution"] == original


@pytest.mark.parametrize("passed", [False, None])
def test_closeout_rejects_nonpassing_incremental_entry_despite_overall_pass(python_exe, tmp_path, passed):
    repo = copy_fixture(tmp_path)
    prepare_release(repo)
    seed_verify_branch(python_exe, repo)
    path = repo / "changes/unreleased/1.3.0/verification-report.json"
    report = json.loads(path.read_text())
    item = report["results"][-1]
    item["incremental"] = {"original": dict(item), "runs": [], "reused": [], "reason": "待补验"}
    if passed is None:
        item.pop("passed")
    else:
        item["passed"] = passed
    path.write_text(json.dumps(report))
    git(repo, "add", str(path))
    git(repo, "commit", "-m", "test: 保存尚未通过的增量条目")
    result = mdf(python_exe, *release_arguments(repo))
    assert result.returncode != 0
    assert "verification_report_not_reusable" in result.stderr
    assert not (repo / "changes/1.3.0/CHANGE.md").exists()


def test_closeout_rejects_removed_semantic_attestation_argument(
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
        "--semantic-attestation-json",
        "{}",
    )
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr


def test_closeout_never_executes_verification_without_reusable_full(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    patch_module_command(
        repo, "release", lambda c: "touch verification-marker && " + c
    )
    prepare_release(repo)
    arguments = release_arguments(repo)

    preview = payload(mdf(python_exe, *arguments, "--dry-run"))
    assert preview["summary"]["verification"]["executed"] is False
    assert not (repo / "verification-marker").exists()

    result = mdf(python_exe, *arguments)
    assert result.returncode != 0
    assert "verification_report_not_reusable" in result.stderr
    assert not (repo / "verification-marker").exists()
    assert not (repo / "changes" / "1.3.0").exists()


def test_closeout_rejects_unclassified_unreleased_bug_on_apply(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo, previous_release=True)
    write_unreleased_change(repo, "service-health")
    replace(
        repo / "changes" / "unreleased" / "service-health" / "CHANGE.md",
        f"fixed: [{BUG_ID}]",
        "fixed: []",
    )
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 遗漏未发布 Bug")
    git(repo, "checkout", "-b", "release/1.3.0")
    seed_verify_branch(python_exe, repo)

    result = mdf(python_exe, *release_arguments(repo))
    assert result.returncode != 0
    assert "unclassified_unreleased_bug" in result.stderr
    assert not (repo / "changes" / "1.3.0").exists()


def test_critical_bug_cannot_be_wont_fixed_at_closeout(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(repo / "docs/bugs" / BUG_NAME, "severity: major", "severity: critical")
    replace(
        repo / "docs/bugs" / BUG_NAME,
        "status: open",
        "status: rejected\nreject-reason: wont-fix",
    )
    init_git(repo, previous_release=True)
    write_unreleased_change(repo, "timeout-close")
    change = repo / "changes" / "unreleased" / "timeout-close" / "CHANGE.md"
    replace(change, f"fixed: [{BUG_ID}]", "fixed: []")
    replace(change, "closed: []", f"closed: [{BUG_ID}]")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: critical wont-fix")
    git(repo, "checkout", "-b", "release/1.3.0")
    seed_verify_branch(python_exe, repo)

    result = mdf(python_exe, *release_arguments(repo))
    assert result.returncode != 0
    assert "critical_bug_blocks_release" in result.stderr


def prepare_wont_fix_release(repo: Path) -> None:
    replace(
        repo / "docs/bugs" / BUG_NAME,
        "status: open",
        "status: rejected\nreject-reason: wont-fix",
    )
    init_git(repo, previous_release=True)
    write_unreleased_change(repo, "service-health")
    change = repo / "changes" / "unreleased" / "service-health" / "CHANGE.md"
    replace(change, f"fixed: [{BUG_ID}]", "fixed: []")
    replace(change, "closed: []", f"closed: [{BUG_ID}]")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: major wont-fix")
    git(repo, "checkout", "-b", "release/1.3.0")


def test_major_bug_wont_fix_needs_explicit_acceptance(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    prepare_wont_fix_release(repo)
    seed_verify_branch(python_exe, repo)

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
    seed_verify_branch(python_exe, accepted_repo)
    applied = payload(
        mdf(
            python_exe,
            *release_arguments(
                accepted_repo, deferred_acceptance_json=acceptance
            ),
        )
    )
    assert applied["outcomes"]["closed"] == [BUG_ID]
    archived = accepted_repo / "docs/bugs" / "archive" / "1.3" / BUG_NAME
    assert archived.is_file()
    assert "reject-reason: wont-fix" in archived.read_text(encoding="utf-8")


def test_hotfix_closeout_uses_manifest_commands(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(repo / "docs/bugs" / BUG_NAME, "status: open", "status: closed\nfixed_in: 1.2.1")
    init_git(repo, previous_release=True)
    git(repo, "checkout", "-b", "hotfix/1.2.1")
    review = repo / "changes/unreleased/1.2.1"
    review.mkdir(parents=True)
    (review / "code-review.md").write_text("# 审查\n\n通过。\n", encoding="utf-8")
    git(repo, "add", "--", "changes/unreleased/1.2.1")
    git(repo, "commit", "-m", "docs: 热修复审查记录")
    seed_verify_branch(python_exe, repo)
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
    assert applied["verification"]["reused"] == (
        "changes/unreleased/1.2.1/verification-report.json"
    )
    assert applied["version"] == "1.2.1"
    assert (repo / "changes" / "1.2.1" / "CHANGE.md").is_file()
    assert (repo / "changes" / "1.2.1" / "code-review.md").is_file()
    assert not review.exists()
    assert (repo / "docs/bugs" / "archive" / "1.2" / BUG_NAME).is_file()


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


def test_closeout_reuses_valid_verify_branch_evidence(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    runs = tmp_path / "release-runs"
    patch_module_command(
        repo, "release", lambda c: f"echo run >> {runs} && " + c
    )
    prepare_release(repo)
    review = repo / "changes/unreleased/1.3.0/code-review.md"
    review.parent.mkdir(parents=True)
    review.write_text("# 审查记录\n\n无未解决问题。\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 审查记录")
    payload(mdf(python_exe, "verify", "--scope", "branch", "--repo", str(repo)))
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 提交验证证据")
    assert runs.read_text() == "run\n"

    applied = payload(mdf(python_exe, *release_arguments(repo)))
    assert applied["verification"]["reused"] == (
        "changes/unreleased/1.3.0/verification-report.json"
    )
    assert runs.read_text() == "run\n"
    assert any(
        item.get("report", {}).get("suite") == "release"
        for item in applied["verification"]["results"]
    )


def test_closeout_reuses_evidence_with_recorded_playbook(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    rel = "tests/playbooks/live.md"
    (repo / "tests/playbooks").mkdir(parents=True)
    (repo / rel).write_text("---\nsuites: [release]\n---\n\n# live\n\n## S01 冒烟\n\n- 判定：通过。\n")
    prepare_release(repo)
    seed = payload(mdf(python_exe, "verify", "branch", "--repo", str(repo)))
    report_dir = seed["result"]["pending"]["report_dir"]
    (repo / report_dir / "live.xml").write_text(
        f'<testsuite name="release"><testcase classname="{rel}" name="S01"/></testsuite>'
    )
    payload(mdf(python_exe, "verify", "branch", "--record", report_dir, "--repo", str(repo)))
    review = repo / "changes/unreleased/1.3.0/code-review.md"
    review.write_text("# 审查记录\n\n无未解决问题。\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 提交验证证据")
    applied = payload(mdf(python_exe, *release_arguments(repo)))
    assert applied["verification"]["results"][-1]["command"] == f"playbook:{rel}"


def test_closeout_reuses_after_impl_change_when_report_still_green(
    python_exe: str, tmp_path: Path
):
    """不以 commit 对齐作废报告；命令序列未变则仍可复用。"""
    repo = copy_fixture(tmp_path)
    runs = tmp_path / "release-runs"
    patch_module_command(
        repo, "release", lambda c: f"echo run >> {runs} && " + c
    )
    prepare_release(repo)
    review = repo / "changes/unreleased/1.3.0/code-review.md"
    review.parent.mkdir(parents=True)
    review.write_text("# 审查记录\n\n无未解决问题。\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 审查记录")
    payload(mdf(python_exe, "verify", "--scope", "branch", "--repo", str(repo)))
    (repo / "src/extra.py").write_text("changed = True\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 证据之后修改实现")

    applied = payload(mdf(python_exe, *release_arguments(repo)))
    assert applied["verification"]["reused"] == (
        "changes/unreleased/1.3.0/verification-report.json"
    )
    assert runs.read_text() == "run\n"


def test_closeout_fails_when_command_sequence_mismatches(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    runs = tmp_path / "release-runs"
    patch_module_command(
        repo, "release", lambda c: f"echo run >> {runs} && " + c
    )
    prepare_release(repo)
    review = repo / "changes/unreleased/1.3.0/code-review.md"
    review.parent.mkdir(parents=True)
    review.write_text("# 审查记录\n\n无未解决问题。\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 审查记录")
    payload(mdf(python_exe, "verify", "--scope", "branch", "--repo", str(repo)))
    path = repo / "changes/unreleased/1.3.0/verification-report.json"
    evidence = json.loads(path.read_text())
    # 伪造与当前 plan 不一致的 command；closeout 不得重跑验证
    for item in evidence["results"]:
        if item.get("id") in {"release", "release:default"}:
            item["command"] = "echo forged-mismatch"
    path.write_text(json.dumps(evidence) + "\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 伪造命令序列")
    assert runs.read_text() == "run\n"

    result = mdf(python_exe, *release_arguments(repo))
    assert result.returncode != 0
    assert "verification_report_not_reusable" in result.stderr
    assert runs.read_text() == "run\n"


@pytest.mark.parametrize("pending", [True, False])
def test_closeout_requires_bug_closed_for_matching_version(python_exe, tmp_path, pending):
    repo = copy_fixture(tmp_path)
    prepare_release(repo)
    bug = repo / "docs/bugs" / BUG_NAME
    if pending:
        replace(bug, "status: closed\nfixed_in: 1.3.0", "status: fixed")
    else:
        replace(bug, "fixed_in: 1.3.0", "fixed_in: 1.4.0")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 未验收或交付版本不符")
    seed_verify_branch(python_exe, repo)
    before = bug.read_text()
    result = mdf(python_exe, *release_arguments(repo))
    assert result.returncode != 0 and "invalid_closure" in result.stderr
    assert bug.read_text() == before
    assert not (repo / "docs/bugs/archive/1.3" / BUG_NAME).exists()
