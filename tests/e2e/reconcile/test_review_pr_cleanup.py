"""PR cleanup 必须在第一次删除 source 之前持久化恢复点。"""
import json
import pytest

from mdf_test_support import git, payload
from support_reconcile import repository, change, prepare, spec_file, apply, call, proof
from support_github_flow import error_of
from test_channels import platform_for


def test_pr_cleanup_resumes_when_source_deletion_interrupts(python_exe, tmp_path, monkeypatch):
    from mdf_core.lifecycle import pull_finish
    from mdf_core.foundation.errors import MDFError
    from mdf_core.reconciliation.context import state_path
    repo = repository(tmp_path, github=False, pr=True, remote=True)
    head = change(repo)
    git(repo, "tag", "v1.3.0")
    git(repo, "push", "origin", "master", "--tags")
    platform = platform_for(repo, tmp_path, monkeypatch)
    work = prepare(python_exe, repo)
    source = git(work, "branch", "--show-current").stdout.strip()
    path = state_path(work, source)
    payload(apply(python_exe, work, spec_file(tmp_path, work, head)))
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(proof(work)))
    payload(call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence)))
    platform.merge(1, tmp_path)
    original = pull_finish.cleanup

    def interrupt(repo, state):
        original(repo, state)
        raise MDFError("PR 删除 source 后中断", code="test_cleanup_interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(pull_finish, "cleanup", interrupt)
        failed = call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence))
    assert error_of(failed)["error"] == "test_cleanup_interrupted"
    assert json.loads(path.read_text()).get("cleanup")
    git(repo, "merge-base", "--is-ancestor", "master", "develop")
    assert payload(call(python_exe, work, "finish", "--source", source, "--yolo"))["result"]["completed"]
    assert not work.exists()


@pytest.mark.parametrize("advance_trunk", [False, True])
def test_support_sync_cleanup_journal_resumes_before_hotfix_closeout(python_exe, tmp_path, monkeypatch, advance_trunk):
    from mdf_core.lifecycle import pull_finish
    from mdf_core.foundation.errors import MDFError
    from mdf_core.reconciliation.context import state_path
    from support_delivery import commit
    repo = repository(tmp_path, pr=True, remote=True)
    git(repo, "branch", "support/1.2", "v1.2.0")
    git(repo, "push", "origin", "support/1.2")
    git(repo, "switch", "-c", "hotfix/1.2.1", "support/1.2")
    head = change(repo)
    platform = platform_for(repo, tmp_path, monkeypatch)
    prepare(python_exe, repo, "1.2.1", "--support", "1.2")
    spec = spec_file(tmp_path, repo, head)
    data = json.loads(spec.read_text())
    data["changes"][0].update(release_notes={"Fixed": ["维护线紧急修复"]}, fixed=["bug-CD34"])
    data["trunk_fixes"] = [{"bug_id": "bug-CD34", "trunk_disposition": "urgent_support_first",
                            "reason": "紧急修复已核验", "released_in": "1.2.1"}]
    spec.write_text(json.dumps(data))
    payload(apply(python_exe, repo, spec, "1.2.1"))
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(proof(repo)))
    payload(call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence)))
    if advance_trunk:
        peer = tmp_path / "peer"
        git(tmp_path, "clone", str(tmp_path / "origin.git"), str(peer))
        bug = peer / "docs/bugs/bug-CD34-unreleased-timeout.md"
        bug.write_text(bug.read_text().replace("status: open", "status: closed\nfixed_in: 1.3.0"))
        commit(peer)
        git(peer, "push", "origin", "master")
    platform.merge(1, tmp_path)
    original = pull_finish.cleanup

    def interrupt(repo, state):
        original(repo, state)
        raise MDFError("同步 PR 删除 source 后中断", code="test_cleanup_interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(pull_finish, "cleanup", interrupt)
        failed = call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence))
    assert error_of(failed)["error"] == "test_cleanup_interrupted"
    assert json.loads(state_path(repo).read_text()).get("sync_cleanup")
    done = payload(call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence)))["result"]
    assert done["completed"]
    assert "1.2.1" in git(repo, "show", "master:CHANGELOG.md").stdout
