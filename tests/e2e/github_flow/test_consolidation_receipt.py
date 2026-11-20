"""consolidate receipt 只能证明本次文档事务，不能接纳 hook 或并发实现。"""
import json
from pathlib import Path

import pytest
from mdf_test_support import git, mdf, payload
from support_delivery import commit
from support_github_flow import error_of
from support_release_flow import prepared_release


@pytest.mark.parametrize("github", [False, True])
@pytest.mark.parametrize("previous", [False, True])
@pytest.mark.parametrize("disturbance", ["hook", "after_commit"])
def test_consolidation_reopens_acceptance_for_unreviewed_commit(
    python_exe, tmp_path, monkeypatch, github, previous, disturbance,
):
    from mdf_core.lifecycle import consolidation, catchup, target_integration
    repo, _, work, _ = prepared_release(python_exe, tmp_path, monkeypatch, github=github, consolidate=previous)
    source = "release/1.3.0"
    root = work / "changes" / ("1.3.0" if previous else "unreleased/1.3.0")
    if previous:
        objective = root / "objectives.md"
        objective.write_text(objective.read_text().replace("[x] consolidate", "[ ] consolidate"))
        commit(work)
    receipt_path = consolidation.record_path(work, source)
    prior_receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
    integration_path = target_integration.state_path(work, source)
    integration_before = integration_path.read_text() if integration_path.is_file() else None
    sync_before = json.loads(catchup.state_path(work, source).read_text())
    original = consolidation.git
    hook = None

    def after_commit(at, *args, **kwargs):
        result = original(at, *args, **kwargs)
        if args[0] == "commit":
            (work / "src/unreviewed.py").write_text("unreviewed = True\n")
            commit(work)
        return result

    with monkeypatch.context() as patch:
        if disturbance == "after_commit":
            patch.setattr(consolidation, "git", after_commit)
        else:
            hooks = repo / ".git/consolidation-hooks"
            hooks.mkdir()
            git(repo, "config", "core.hooksPath", str(hooks))
            hook = hooks / "pre-commit"
            hook.write_text("#!/bin/sh\nprintf 'unreviewed = True\\n' > src/unreviewed.py\ngit add src/unreviewed.py\n")
            hook.chmod(0o755)
        result = mdf(python_exe, "consolidate", "--repo", str(work), "--release-date", "2026-11-20")
    assert result.returncode != 0
    assert (work / "src/unreviewed.py").read_text() == "unreviewed = True\n"
    receipt = json.loads(receipt_path.read_text())
    assert receipt.get("pending") is True
    assert receipt.get("head") == prior_receipt.get("head")
    assert (integration_path.read_text() if integration_path.is_file() else None) == integration_before
    reopened = json.loads(catchup.state_path(work, source).read_text())
    assert "completed_head" not in reopened
    assert reopened["base"] == sync_before.get("completed_head", sync_before["base"])
    route = payload(mdf(python_exe, "delivery", "route", "--repo", str(work)))["result"]
    assert route["next"] == "catch-up"
    if hook:
        hook.unlink()
    if git(work, "status", "--porcelain").stdout.strip():
        git(work, "add", "-A")
        if git(work, "diff", "--cached", "--name-only").stdout.strip():
            commit(work)
    assert error_of(mdf(python_exe, "consolidate", "--repo", str(work), "--release-date", "2026-11-20"))["error"] == "catchup_required"
    assert mdf(python_exe, "merge", "--repo", str(work)).returncode != 0
    review = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    assert review["plan"]["review"]["action"] != "skip"
    assert "src/unreviewed.py" in review["plan"]["verify"]["paths"]
    payload(mdf(python_exe, "catch-up", "--repo", str(work), "--complete", "--reviewed-head", review["head"],
                "--summary", "对新增实现完成 incr-cr、smart 与 incr-fa"))
    route = payload(mdf(python_exe, "delivery", "route", "--repo", str(work)))["result"]
    assert route["next"] == "consolidate"
    done = payload(mdf(python_exe, "consolidate", "--repo", str(work), "--release-date", "2026-11-20"))
    receipt = json.loads(receipt_path.read_text())
    assert receipt["head"] == done["head"] and not receipt.get("pending")
    if github:
        payload(mdf(python_exe, "publish", "--repo", str(work)))
    assert payload(mdf(python_exe, "merge", "--repo", str(work)))["completed"]
