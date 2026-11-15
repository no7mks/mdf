"""delivery route / complete-stage：等待状态显式保留，自动完成只提交本阶段文件且幂等。"""
import pytest

from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from support_github_flow import error_of
from test_catch_up_plan import started


def set_steps(work, root, steps):
    body = "".join(f"- [{'x' if done else ' '}] {name}\n" for name, done in steps)
    (root / "objectives.md").write_text("# 目标\n\n- needs_design: no\n\n" + body)
    commit(work, "docs: 更新清单")


def route(python_exe, work, *extra):
    return payload(mdf(python_exe, "delivery", "route", "--repo", str(work), *extra))["result"]


def complete(python_exe, work, stage):
    return mdf(python_exe, "delivery", "complete-stage", "--repo", str(work), "--stage", stage)


def passing_report(root, branch="feature/service-health", scope="branch"):
    (root / "verification-report.json").write_text(json.dumps({
        "all_passed": True, "branch": branch, "scope": scope,
        "suites": ["quick", "smoke"], "results": [{"command": "true", "exit_code": 0}],
    }))


@pytest.mark.parametrize("steps,yolo,state,nxt", [
    ([("design", False)], False, "awaiting_design_approval", None),
    ([("design", False)], True, "ready", None),
    ([("人工工作", False)], True, "awaiting_manual_work", None),
    ([("lint", True), ("close-out", False)], False, "awaiting_decision_confirmation", None),
    ([("pr", False)], False, "awaiting_decision_confirmation", None),
    ([("close-out", False)], True, "ready", None),
    ([("lint", False)], False, "ready", None),
    ([("lint", True), ("close-out", True)], False, "awaiting_decision_confirmation", "close-out"),
])
def test_route_keeps_confirmation_and_manual_nodes(python_exe, tmp_path, steps, yolo, state, nxt):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, steps)
    result = route(python_exe, work, *(["--yolo"] if yolo else []))
    assert result["state"] == state
    assert result["next"] == (nxt if nxt is not None else next((n for n, done in steps if not done), None))


def test_route_marks_verify_auto_completable_only_with_passing_report(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("verify branch", False)])
    assert route(python_exe, work)["auto_completable"] is False
    passing_report(root, "someone-else")
    assert route(python_exe, work)["auto_completable"] is False
    passing_report(root)
    assert route(python_exe, work)["auto_completable"] is True


def test_complete_verify_commits_only_stage_files_and_is_idempotent(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("verify branch", False), ("fact audit", False)])
    passing_report(root)
    (work / "notes.txt").write_text("用户的无关改动\n")
    first = payload(complete(python_exe, work, "verify"))["result"]
    assert first["completed"] and not first["already_completed"]
    committed = git(work, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert sorted(committed) == sorted([f"{root.relative_to(work)}/objectives.md",
                                        f"{root.relative_to(work)}/verification-report.json"])
    assert "- [x] verify branch" in (root / "objectives.md").read_text()
    assert (work / "notes.txt").exists() and "notes.txt" in git(work, "status", "--porcelain").stdout
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    again = payload(complete(python_exe, work, "verify"))["result"]
    assert again["already_completed"] is True and git(work, "rev-parse", "HEAD").stdout.strip() == head


def test_playbook_verification_records_clear_after_committing_its_report(python_exe, tmp_path):
    from test_playbooks import _write_junit, _write_playbook

    repo, _, _ = started(python_exe, tmp_path)
    release = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "release",
                          "--version", "1.3.0", "--objectives-file", str(write_release_objectives(tmp_path))))
    work = Path(release["worktree"])
    root = work / "changes/unreleased/1.3.0"
    _write_playbook(work, "release.md", "[release]", ("S01",))
    set_steps(work, root, [("verify branch", False)])
    command = ("verify", "branch", "--repo", str(work))
    pending = payload(mdf(python_exe, *command))["result"]["pending"]
    folder = pending["report_dir"]
    _write_junit(work, folder, "release", [("tests/playbooks/release.md", "S01", False)])
    payload(mdf(python_exe, *command, "--record", folder))
    state = repo / ".git/mdf/clear-commits.json"
    assert not state.exists()
    payload(complete(python_exe, work, "verify"))
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    assert json.loads(state.read_text())["verify_release"] == head
    rerun = payload(mdf(python_exe, *command))["result"]
    assert rerun["all_passed"] and rerun["results"][-1]["clear_commit"] == head


def test_verify_requires_matching_scope_branch_and_earlier_steps(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("code-review", False), ("verify branch", False)])
    passing_report(root, scope="smart")
    assert route(python_exe, work)["auto_completable"] is False
    error = error_of(complete(python_exe, work, "verify"))
    assert error["error"] == "stage_evidence_missing"
    assert error["details"]["expected_scope"] == "branch" and error["details"]["actual_scope"] == "smart"
    (root / "verification-report.json").write_text(json.dumps({"all_passed": True, "scope": "branch"}))
    assert error_of(complete(python_exe, work, "verify"))["details"]["actual_branch"] is None
    passing_report(root)
    prerequisite = error_of(complete(python_exe, work, "verify"))
    assert prerequisite["error"] == "stage_prerequisite" and prerequisite["details"]["pending"] == ["code-review"]


def test_verify_smart_needs_smart_scope_and_branch_summary_is_committed_when_present(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("verify smart", False)])
    passing_report(root)
    assert error_of(complete(python_exe, work, "verify"))["details"]["expected_scope"] == "smart"
    passing_report(root, scope="smart")
    assert payload(complete(python_exe, work, "verify"))["result"]["completed"]
    set_steps(work, root, [("verify branch", False)])
    passing_report(root)
    (root / "verification-report.md").write_text("架构审视要点\n")
    done = payload(complete(python_exe, work, "verify"))["result"]
    assert sorted(Path(p).name for p in done["paths"]) == ["objectives.md", "verification-report.json",
                                                            "verification-report.md"]


def test_unrelated_staged_changes_abort_and_preserve_the_scene(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("verify branch", False)])
    passing_report(root)
    (work / "staged.txt").write_text("别人暂存的内容\n")
    git(work, "add", "staged.txt")
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    objectives = (root / "objectives.md").read_text()
    error = error_of(complete(python_exe, work, "verify"))
    assert error["error"] == "unrelated_staged_changes"
    assert error["details"]["paths"] == ["staged.txt"]
    assert git(work, "rev-parse", "HEAD").stdout.strip() == head
    assert git(work, "diff", "--cached", "--name-only").stdout.split() == ["staged.txt"]
    assert (root / "objectives.md").read_text() == objectives


@pytest.mark.parametrize("stage,code", [("verify", "stage_evidence_missing"), ("converge", "invalid_stage")])
def test_stage_without_evidence_or_not_pure_evidence_is_refused(python_exe, tmp_path, stage, code):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("verify branch", False), ("converge", False)])
    assert error_of(complete(python_exe, work, stage))["error"] == code
    assert "- [ ] verify branch" in (root / "objectives.md").read_text()


def test_catch_up_completes_on_zero_increment_and_records_baseline(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("fact audit", True), ("catch-up", False)])
    base = git(work, "rev-parse", "HEAD").stdout.strip()
    assert route(python_exe, work)["auto_completable"] is True
    done = payload(complete(python_exe, work, "catch-up"))["result"]
    assert done["completed"] and done["evidence"] == {"baseline": base}
    text = (root / "objectives.md").read_text()
    assert "- [x] catch-up" in text and f"catch-up 基线：{base}" in text
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    assert payload(complete(python_exe, work, "catch-up"))["result"]["already_completed"] is True
    assert git(work, "rev-parse", "HEAD").stdout.strip() == head


def test_catch_up_refuses_when_increment_needs_work(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("fact audit", True), ("catch-up", False)])
    (work / "src/service.py").write_text("VALUE = 2\n")
    commit(work, "fix: 返工")
    assert route(python_exe, work)["auto_completable"] is False
    error = error_of(complete(python_exe, work, "catch-up"))
    assert error["error"] == "stage_evidence_missing"
    assert "- [ ] catch-up" in (root / "objectives.md").read_text()


def test_pr_mode_routes_to_platform_verification(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    manifest = work / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() + "closeout:\n  mode: pr\n  provider: github\n", encoding="utf-8")
    commit(work, "chore: 启用 pr mode")
    set_steps(work, root, [("lint", True)])
    assert route(python_exe, work) == {**route(python_exe, work), "next": "pr",
                                        "state": "awaiting_decision_confirmation"}
    assert route(python_exe, work, "--yolo")["state"] == "ready"
    record = work / ".git"
    assert record.is_file()  # linked worktree 的 Git 元数据由主仓共享
    common = Path(git(work, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    old = common / "mdf/finish/feature/service-health.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({"merge_commit": "a" * 40, "completed": True}))
    assert route(python_exe, work)["next"] == "pr"


def test_complete_stage_rejects_missing_suite_empty_results_merge_and_dirty_code(python_exe, tmp_path):
    repo, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("verify branch", False)])
    (root / "verification-report.json").write_text(json.dumps(
        {"all_passed": True, "branch": "feature/service-health", "scope": "branch", "suites": ["quick"]}))
    assert route(python_exe, work)["auto_completable"] is False
    set_steps(work, root, [("verify smart", False)])
    (root / "verification-report.json").write_text(json.dumps(
        {"all_passed": True, "branch": "feature/service-health", "scope": "smart", "results": []}))
    assert route(python_exe, work)["auto_completable"] is False
    set_steps(work, root, [("fact audit", True), ("catch-up", False)])
    (work / "src/service.py").write_text("dirty = True\n")
    assert error_of(complete(python_exe, work, "catch-up"))["error"] == "dirty_worktree"
    (work / "src/service.py").unlink()
    from test_catch_up_plan import upstream
    upstream(repo, "later.txt", "上游\n")
    assert run(["git", "merge", "--no-ff", "--no-commit", "develop"], cwd=work).returncode == 0
    assert error_of(complete(python_exe, work, "catch-up"))["error"] == "unfinished_merge"
    run(["git", "merge", "--abort"], cwd=work)
    set_steps(work, root, [("verify branch", False)])
    passing_report(root)
    text = (root / "objectives.md").read_text().replace("- [ ] verify branch", "- [x] verify branch")
    (root / "objectives.md").write_text(text)
    git(work, "add", "changes/unreleased/service-health/objectives.md",
        "changes/unreleased/service-health/verification-report.json")
    done = payload(complete(python_exe, work, "verify"))["result"]
    assert done["completed"] and not done["already_completed"]


def test_catch_up_requires_earlier_steps(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("fact audit", True), ("verify branch", False), ("catch-up", False)])
    assert error_of(complete(python_exe, work, "catch-up"))["error"] == "stage_prerequisite"


@pytest.mark.parametrize("result", [{"passed": False}, {}, {"passed": False, "exit_code": 0}])
def test_smart_refuses_unsuccessful_result(python_exe, tmp_path, result):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("verify smart", False)])
    (root / "verification-report.json").write_text(json.dumps({
        "all_passed": True, "branch": "feature/service-health", "scope": "smart", "results": [result],
    }))
    assert route(python_exe, work)["auto_completable"] is False
    assert error_of(complete(python_exe, work, "verify"))["error"] == "stage_evidence_missing"
