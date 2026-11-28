"""固定 tag、远端前进与连续历史版本的幂等续办。"""
import json
from pathlib import Path
import pytest

from mdf_test_support import git, payload
from support_reconcile import repository, change, prepare, spec_file, apply, call, proof
from support_github_flow import error_of, has_ref


def candidate(python_exe, tmp_path):
    repo = repository(tmp_path, remote=True)
    git(repo, "switch", "-c", "release/1.3.0")
    head = change(repo)
    prepare(python_exe, repo)
    payload(apply(python_exe, repo, spec_file(tmp_path, repo, head)))
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(proof(repo)))
    return repo, tmp_path / "origin.git", evidence


def test_target_advance_requires_incremental_acceptance_without_moving_tag(python_exe, tmp_path):
    repo, remote, evidence = candidate(python_exe, tmp_path)
    fixed = git(repo, "rev-parse", "HEAD").stdout.strip()
    peer = tmp_path / "peer"
    git(tmp_path, "clone", str(remote), str(peer))
    incoming = change(peer, "target_advance")
    git(peer, "push", "origin", "master")
    failed = call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence))
    assert error_of(failed)["error"] == "integration_required"
    assert error_of(failed)["details"]["verify"]["action"] == "smart"
    pending = payload(call(python_exe, repo, "inspect"))["result"]
    assert pending["resume"] and pending["record_mode"] == "ledgerless"
    assert payload(call(python_exe, repo, "prepare"))["result"]["source"] == "release/1.3.0"
    tag_oid = git(remote, "rev-parse", "v1.3.0").stdout.strip()
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == fixed
    assert error_of(call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence)))["error"] == "external_evidence_required"
    evidence.write_text(json.dumps(proof(repo)))
    done = payload(call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence)))["result"]
    assert done["completed"]
    assert git(remote, "rev-parse", "v1.3.0").stdout.strip() == tag_oid
    git(remote, "merge-base", "--is-ancestor", incoming, "master")


def test_external_tag_is_never_overwritten(python_exe, tmp_path):
    repo, remote, evidence = candidate(python_exe, tmp_path)
    git(remote, "tag", "v1.3.0", "master")
    before = git(remote, "rev-parse", "v1.3.0").stdout
    failed = call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence))
    assert error_of(failed)["error"] == "tag_conflict"
    assert git(remote, "rev-parse", "v1.3.0").stdout == before
    assert not has_ref(remote, "refs/heads/release/1.3.0")


def test_multiple_missing_versions_are_recorded_once(python_exe, tmp_path):
    repo = repository(tmp_path)
    initial = git(repo, "rev-parse", "HEAD").stdout.strip()
    middle = change(repo, "middle")
    git(repo, "tag", "v1.3.0")
    last = change(repo, "last")
    git(repo, "tag", "v1.4.0")
    data = payload(call(python_exe, repo, "prepare"))["result"]
    assert [r["version"] for r in data["releases"]] == ["1.2.0", "1.3.0", "1.4.0"]
    work = Path(data["worktree"])
    for version, head in (("1.2.0", initial), ("1.3.0", middle), ("1.4.0", last)):
        spec = spec_file(tmp_path, work, head)
        day = "2026-11-28"
        if version == "1.2.0":
            body = json.loads(spec.read_text())
            body["changes"][0]["release_notes"] = {"Added": ["提供可验证的服务状态。"]}
            spec.write_text(json.dumps(body))
            day = "2026-01-02"
        payload(call(python_exe, work, "apply", "--version", version, "--release-date", day, "--record-file", str(spec)))
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(proof(work)))
    payload(call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence)))
    assert payload(call(python_exe, repo, "inspect"))["result"]["releases"] == []
    text = (repo / "CHANGELOG.md").read_text()
    assert text.count("## [1.3.0]") == text.count("## [1.4.0]") == 1
    repeated = payload(call(python_exe, repo, "prepare", "--version", "1.3.0"))["result"]
    assert repeated["completed"] and repeated["worktree"] == str(repo)
    assert not git(repo, "branch", "--list", "pm/*").stdout.strip()


@pytest.mark.parametrize("advance", [False, True])
def test_gitflow_publish_retry_keeps_actual_merged_source(python_exe, tmp_path, monkeypatch, advance):
    from mdf_core.reconciliation import finish
    from mdf_core.foundation.errors import MDFError
    repo = repository(tmp_path, github=False, remote=True)
    git(repo, "switch", "-c", "release/1.3.0")
    head = change(repo)
    prepare(python_exe, repo)
    payload(apply(python_exe, repo, spec_file(tmp_path, repo, head)))
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(proof(repo)))

    def fail_publish(*args, **kwargs):
        raise MDFError("发布前中断", code="test_publish_interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(finish, "tag_release", fail_publish)
        failed = call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence))
    assert error_of(failed)["error"] == "test_publish_interrupted"
    remote = tmp_path / "origin.git"
    merged = git(remote, "rev-parse", "master").stdout.strip()
    if advance:
        change(repo, "after_merge")
        evidence.write_text(json.dumps(proof(repo)))
    result = call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence))
    if advance:
        assert error_of(result)["error"] == "pull_state_changed"
        assert not has_ref(remote, "refs/tags/v1.3.0")
    else:
        assert payload(result)["result"]["completed"]
        assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == merged


def test_unpublished_candidate_cannot_rewind_new_remote_source(python_exe, tmp_path, monkeypatch):
    from mdf_core.reconciliation import finish
    from mdf_core.foundation.errors import MDFError
    repo, remote, evidence = candidate(python_exe, tmp_path)

    def fail_publish(*args, **kwargs):
        raise MDFError("发布前中断", code="test_publish_interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(finish, "tag_release", fail_publish)
        failed = call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence))
    assert error_of(failed)["error"] == "test_publish_interrupted"
    shared = change(repo, "shared_after_attempt")
    git(repo, "push", "origin", "release/1.3.0")
    evidence.write_text(json.dumps(proof(repo)))
    failed = call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence))
    assert error_of(failed)["error"] == "release_head_changed"
    assert git(remote, "rev-parse", "release/1.3.0").stdout.strip() == shared
    assert not has_ref(remote, "refs/tags/v1.3.0")
