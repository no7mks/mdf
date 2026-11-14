"""未发布修复声明必须与 Bug 当前状态一致，合入入口不得放过漏改状态。"""
from types import SimpleNamespace

import pytest

from mdf_core.foundation.errors import MDFError
from mdf_core.inspection.validate_records import validate_record_references


def write_outcome(repo, status, *, root="unreleased", source="bugfix/bug-0001"):
    bug = repo / "docs/bugs/bug-0001-example.md"
    bug.parent.mkdir(parents=True, exist_ok=True)
    bug.write_text(f"---\nid: bug-0001\ntype: bug\nstatus: {status}\n---\n")
    change = repo / "changes" / root / "bug-0001/CHANGE.md"
    change.parent.mkdir(parents=True, exist_ok=True)
    change.write_text(f"---\nsource_branch: {source}\nfixed: [bug-0001]\n---\n")
    return bug, change


@pytest.mark.parametrize("status", ["open", "rejected", "fixed", "closed"])
def test_fixed_outcome_status(tmp_path, status):
    _, change = write_outcome(tmp_path, status)
    findings = []
    validate_record_references(tmp_path, findings)
    mismatches = [item for item in findings if item.code == "change.fixed_status"]
    assert bool(mismatches) == (status in {"open", "rejected"})
    if mismatches:
        assert mismatches[0].path == change.relative_to(tmp_path).as_posix()


def test_historical_outcome_does_not_constrain_current_status(tmp_path):
    write_outcome(tmp_path, "open", root="1.0.0")
    findings = []
    validate_record_references(tmp_path, findings)
    assert not any(item.code == "change.fixed_status" for item in findings)


@pytest.mark.parametrize("entry", ["local", "pr"])
@pytest.mark.parametrize("status", ["open", "rejected"])
def test_finish_rejects_inconsistent_outcome_before_side_effects(tmp_path, monkeypatch, entry, status):
    from mdf_core.workspace import gitflow
    from mdf_core.lifecycle import pull_finish
    from mdf_core.workspace import merge_policy
    from contextlib import nullcontext

    bug, _ = write_outcome(tmp_path, status)
    before = bug.read_bytes()
    source = "bugfix/bug-0001"
    monkeypatch.setattr(gitflow, "repo_path", lambda value: tmp_path)
    monkeypatch.setattr(gitflow, "require_git_root", lambda repo: None)
    monkeypatch.setattr(gitflow, "ensure_clean", lambda repo: None)
    monkeypatch.setattr(gitflow, "worktree_map", lambda *_: {source: tmp_path})
    monkeypatch.setattr(merge_policy, "local_head", lambda *_: "a" * 40)
    monkeypatch.setattr(pull_finish, "finish_lock", lambda *_: nullcontext())
    monkeypatch.setattr(gitflow, "current_branch", lambda repo: source)
    monkeypatch.setattr(pull_finish, "current_branch", lambda repo: source)
    monkeypatch.setattr(merge_policy, "configured", lambda repo: {"mode": "local"})
    with pytest.raises(MDFError) as caught:
        if entry == "local":
            gitflow.command_finish_gitflow(SimpleNamespace(repo=str(tmp_path), source=None))
        else:
            pull_finish.preflight(tmp_path, source)
    assert caught.value.code == "change.fixed_status"
    assert bug.read_bytes() == before


def test_finish_check_allows_valid_status_and_ignores_other_source(tmp_path):
    from mdf_core.inspection.validate_records import require_fixed_outcomes

    for status in ("fixed", "closed"):
        write_outcome(tmp_path, status)
        require_fixed_outcomes(tmp_path, "bugfix/bug-0001")
    write_outcome(tmp_path, "open", source="bugfix/other")
    require_fixed_outcomes(tmp_path, "bugfix/bug-0001")


def test_pr_recovery_does_not_validate_current_checkout_outcomes(tmp_path, monkeypatch):
    from mdf_core.workspace import gitflow, merge_policy
    from mdf_core.lifecycle import pull_finish

    source = "bugfix/bug-0001"
    write_outcome(tmp_path, "open", source=source)
    monkeypatch.setattr(gitflow, "repo_path", lambda value: tmp_path)
    monkeypatch.setattr(gitflow, "require_git_root", lambda repo: None)
    monkeypatch.setattr(gitflow, "ensure_clean", lambda repo: None)
    monkeypatch.setattr(gitflow, "worktree_map", lambda *_: {source: tmp_path})
    monkeypatch.setattr(pull_finish, "finish_lock", lambda *_: nullcontext())
    monkeypatch.setattr(merge_policy, "configured", lambda repo: {"mode": "pr"})
    calls = []
    monkeypatch.setattr(pull_finish, "finish",
                        lambda repo, branch, settings, **kwargs: calls.append((branch, kwargs["phase"])))
    gitflow.command_finish_gitflow(SimpleNamespace(repo=str(tmp_path), source=source, phase="close-out"))
    assert calls == [(source, "close-out")]
