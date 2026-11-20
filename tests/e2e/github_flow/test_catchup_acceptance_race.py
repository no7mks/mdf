"""catch-up 完成只能接纳明确审过的固定 HEAD。"""
import pytest

from mdf_test_support import git, mdf, payload
from support_delivery import commit
from support_github_flow import error_of
from support_release_flow import prepared_release


def test_catchup_completion_rejects_commit_during_plan(python_exe, tmp_path, monkeypatch):
    from mdf_core.lifecycle import incremental_plan
    from mdf_core.lifecycle.catchup import state_path
    import json
    _, _, work, _ = prepared_release(python_exe, tmp_path, monkeypatch, consolidate=False)
    ready = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    original = incremental_plan.build_plan
    def advance(*args, **kwargs):
        plan = original(*args, **kwargs)
        (work / "src/unreviewed.py").write_text("unreviewed = True\n")
        commit(work)
        return plan
    monkeypatch.setattr(incremental_plan, "build_plan", advance)
    failed = mdf(python_exe, "catch-up", "--repo", str(work), "--complete", "--reviewed-head", ready["head"],
                 "--summary", "只验收当前固定提交")
    assert error_of(failed)["error"] == "sync_review_required"
    assert "completed_head" not in json.loads(state_path(work, "release/1.3.0").read_text())
    assert "- [ ] catch-up" in (work / "changes/unreleased/1.3.0/objectives.md").read_text()
    assert git(work, "rev-parse", "HEAD").stdout.strip() != ready["head"]


@pytest.mark.parametrize("github", [False, True])
def test_catchup_does_not_accept_code_added_by_record_commit_hook(python_exe, tmp_path, monkeypatch, github):
    from pathlib import Path
    from mdf_core.lifecycle.catchup import state_path
    import json
    _, _, work, _ = prepared_release(python_exe, tmp_path, monkeypatch, consolidate=False, github=github)
    ready = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    hooks = Path(git(work, "rev-parse", "--git-path", "hooks").stdout.strip())
    if not hooks.is_absolute():
        hooks = work / hooks
    hooks.mkdir(exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nprintf 'unreviewed = True\\n' > src/unreviewed.py\ngit add src/unreviewed.py\n")
    hook.chmod(0o755)
    failed = mdf(python_exe, "catch-up", "--repo", str(work), "--complete", "--reviewed-head", ready["head"],
                 "--summary", "只验收当前固定提交")
    assert error_of(failed)["error"] == "sync_review_required"
    assert "completed_head" not in json.loads(state_path(work, "release/1.3.0").read_text())
    assert (work / "src/unreviewed.py").is_file()

    route = payload(mdf(python_exe, "delivery", "route", "--repo", str(work)))["result"]
    assert route["next"] == "catch-up"
    blocked = mdf(python_exe, "consolidate", "--repo", str(work))
    assert error_of(blocked)["error"] == "catchup_required"
    hook.unlink()
    review = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    assert review["plan"]["review"]["action"] != "skip"
    payload(mdf(python_exe, "catch-up", "--repo", str(work), "--complete", "--reviewed-head", review["head"],
                "--summary", "重新审阅并验收 hook 加入的增量"))
    route = payload(mdf(python_exe, "delivery", "route", "--repo", str(work)))["result"]
    assert route["next"] == "consolidate"
