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


def passing_report(root, branch="feature/service-health"):
    (root / "verification-report.json").write_text(json.dumps({"all_passed": True, "branch": branch}))


@pytest.mark.parametrize("steps,yolo,state", [
    ([("design", False)], False, "awaiting_design_approval"),
    ([("design", False)], True, "awaiting_design_approval"),
    ([("人工工作", False)], True, "awaiting_manual_work"),
    ([("lint", True), ("close-out", False)], False, "awaiting_decision_confirmation"),
    ([("pr", False)], False, "awaiting_decision_confirmation"),
    ([("close-out", False)], True, "ready"),
    ([("lint", False)], False, "ready"),
    ([("lint", True), ("close-out", True)], False, "complete"),
])
def test_route_keeps_confirmation_and_manual_nodes(python_exe, tmp_path, steps, yolo, state):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, steps)
    result = route(python_exe, work, *(["--yolo"] if yolo else []))
    assert result["state"] == state
    assert result["next"] == next((n for n, done in steps if not done), None)


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


def test_catch_up_requires_earlier_steps(python_exe, tmp_path):
    _, work, root = started(python_exe, tmp_path)
    set_steps(work, root, [("fact audit", True), ("verify branch", False), ("catch-up", False)])
    assert error_of(complete(python_exe, work, "catch-up"))["error"] == "stage_prerequisite"
