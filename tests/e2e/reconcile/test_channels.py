"""两种 workflow × 两种 closeout 的补账合入、CI、backmerge 与清理。"""
import json

import pytest

from mdf_test_support import git, payload, mdf
from support_github_flow import has_ref
from support_reconcile import repository, change, prepare, spec_file, apply, call, proof
from support_pull import Platform


def platform_for(repo, tmp_path, monkeypatch):
    from mdf_core.lifecycle import pull_finish, pull_watch
    platform = Platform()
    platform.repo, platform.remote = repo, tmp_path / "origin.git"
    monkeypatch.setattr(pull_finish, "origin", lambda *_: {})
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    monkeypatch.setattr(pull_watch, "pull_status", lambda forge, number, *_: {
        "pull_request": forge.get(number), "checks": [], "change_requests": [], "conflicts": False,
    })
    return platform


@pytest.mark.parametrize("github", [False, True])
@pytest.mark.parametrize("pr", [False, True])
def test_post_hoc_channel_full_matrix(python_exe, tmp_path, monkeypatch, github, pr):
    repo = repository(tmp_path, github=github, pr=pr, remote=pr)
    released = change(repo)
    git(repo, "tag", "v1.3.0")
    if pr:
        git(repo, "push", "origin", "master", "--tags")
        platform = platform_for(repo, tmp_path, monkeypatch)
    before = git(repo, "rev-parse", "master").stdout.strip()
    work = prepare(python_exe, repo)
    source = git(work, "branch", "--show-current").stdout.strip()
    payload(apply(python_exe, work, spec_file(tmp_path, work, released)))
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(proof(work)))
    result = payload(call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence)))["result"]
    if pr:
        assert not result["completed"] and platform.pulls[0]["target"] == "master"
        source_head = platform.pulls[0]["head"]
        merged = platform.merge(1, tmp_path)
        git(repo, "fetch", "origin")
        from mdf_core.inspection.push_audit import audit
        verdict = audit(repo, "master", before, merged, {"pull_requests": [platform.pulls[0]]})
        assert verdict["verdict"] == "pass", verdict
        result = payload(call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence)))["result"]
        assert not has_ref(tmp_path / "origin.git", f"refs/heads/{source}")
    assert result["completed"]
    assert (repo / "changes/1.3.0/CHANGE.md").exists()
    if not github:
        git(repo, "merge-base", "--is-ancestor", "master", "develop")
    if source != "planning":
        assert not has_ref(repo, f"refs/heads/{source}")
        assert not work.exists()
    assert payload(call(python_exe, repo, "finish", "--source", source, "--yolo"))["result"]["already_completed"]


@pytest.mark.parametrize("github", [False, True])
def test_direct_pr_entry_accepts_reconcile_worktree(python_exe, tmp_path, monkeypatch, github):
    repo = repository(tmp_path, github=github, pr=True, remote=True)
    released = change(repo)
    git(repo, "tag", "v1.3.0")
    git(repo, "push", "origin", "master", "--tags")
    platform_for(repo, tmp_path, monkeypatch)
    work = prepare(python_exe, repo)
    payload(apply(python_exe, work, spec_file(tmp_path, work, released)))
    result = payload(mdf(python_exe, "pr", "--repo", str(work)))
    assert result["status"] == "waiting_for_merge"
    assert result["pull_request"]["target"] == "master"


def test_cleanup_interruption_resumes_after_source_ref_is_deleted(python_exe, tmp_path, monkeypatch):
    from mdf_core.reconciliation import finish
    from mdf_core.reconciliation.context import state_path
    from mdf_core.foundation.errors import MDFError
    from support_github_flow import error_of
    repo = repository(tmp_path)
    released = change(repo)
    git(repo, "tag", "v1.3.0")
    work = prepare(python_exe, repo)
    source = git(work, "branch", "--show-current").stdout.strip()
    path = state_path(work, source)
    payload(apply(python_exe, work, spec_file(tmp_path, work, released)))
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(proof(work)))
    original = finish.cleanup

    def interrupt(repo, state):
        original(repo, state)
        raise MDFError("清理中断", code="test_cleanup_interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(finish, "cleanup", interrupt)
        failed = call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence))
    assert error_of(failed)["error"] == "test_cleanup_interrupted"
    assert not json.loads(path.read_text()).get("completed")
    assert not has_ref(repo, f"refs/heads/{source}") and work.exists()
    assert payload(call(python_exe, work, "finish", "--source", source, "--yolo"))["result"]["completed"]
    assert not work.exists()
