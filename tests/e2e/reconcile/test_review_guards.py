"""独立 review 发现的材料失效、入口降级与清理授权回归。"""
import json

import pytest

from mdf_test_support import git, payload
from support_delivery import commit
from support_github_flow import error_of, has_ref
from support_reconcile import repository, change, prepare, spec_file, apply, call, proof
from test_recovery import candidate


@pytest.mark.parametrize("mutation", ["delete", "changelog", "tag", "tag-object"])
def test_finish_rechecks_archived_material_and_release_identity(python_exe, tmp_path, mutation):
    repo = repository(tmp_path)
    released = change(repo)
    git(repo, "tag", "v1.3.0")
    work = prepare(python_exe, repo)
    payload(apply(python_exe, work, spec_file(tmp_path, work, released)))
    before = git(repo, "rev-parse", "master").stdout
    if mutation == "delete":
        git(work, "rm", "-r", "changes/1.3.0")
        commit(work)
    elif mutation == "changelog":
        path = work / "CHANGELOG.md"
        path.write_text(path.read_text().replace("已核实的外部实现", "另一项未经对账的成果"))
        commit(work)
    elif mutation == "tag":
        git(work, "tag", "-f", "v1.3.0", "HEAD")
    else:
        git(work, "tag", "-f", "-a", "v1.3.0", released, "-m", "替换 tag 对象")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(proof(work)))
    result = call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence))
    assert result.returncode != 0, result.stdout
    assert git(repo, "rev-parse", "master").stdout == before
    assert work.exists()


@pytest.mark.parametrize("record_only", [True, False])
def test_cleanup_resume_still_obeys_record_only_and_confirmation(python_exe, tmp_path, monkeypatch, record_only):
    from mdf_core.reconciliation import finish
    from mdf_core.foundation.errors import MDFError
    repo, remote, evidence = candidate(python_exe, tmp_path)

    def interrupt(*args):
        raise MDFError("删除 source 前中断", code="test_cleanup_interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(finish, "cleanup_remote", interrupt)
        failed = call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence))
    assert error_of(failed)["error"] == "test_cleanup_interrupted"
    source = "release/1.3.0"
    result = payload(call(python_exe, repo, "finish", *(["--record-only"] if record_only else [])))["result"]
    assert not result["completed"]
    assert result.get("record_only") if record_only else result["state"] == "awaiting_publication_confirmation"
    assert has_ref(repo, f"refs/heads/{source}") and has_ref(remote, f"refs/heads/{source}")
    assert payload(call(python_exe, repo, "finish", "--yolo"))["result"]["completed"]


def test_new_code_after_apply_requires_new_reconciliation(python_exe, tmp_path):
    repo, remote, evidence = candidate(python_exe, tmp_path)
    change(repo, "not_recorded")
    evidence.write_text(json.dumps(proof(repo)))
    result = call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence))
    assert result.returncode != 0, result.stdout
    assert not has_ref(remote, "refs/tags/v1.3.0")


def test_empty_apply_cannot_mark_new_implementation_reconciled(python_exe, tmp_path):
    repo, remote, _ = candidate(python_exe, tmp_path)
    head = change(repo, "not_recorded")
    spec = tmp_path / "empty-record.json"
    spec.write_text(json.dumps({"commit": head, "fact": proof(repo)}))
    result = apply(python_exe, repo, spec)
    assert result.returncode != 0, result.stdout
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == head
    assert not has_ref(remote, "refs/tags/v1.3.0")


def test_recorded_candidate_is_protected_but_later_tail_can_squash(python_exe, tmp_path):
    from mdf_core.workspace.squash import check
    from squash_execute import execute
    repo, _, _ = candidate(python_exe, tmp_path)
    recorded = git(repo, "rev-parse", "HEAD").stdout.strip()
    assert check(repo)["floor"] == recorded
    change(repo, "first_after_record")
    change(repo, "second_after_record")
    plan = check(repo)
    assert plan["floor"] == recorded and not plan["noop"]
    plan.update(start_commit=recorded, segments=[{"tip": plan["old_tip"], "message": "test: 整理候选后的增量"}])
    execute(repo.resolve(), plan, False, [])
    git(repo, "merge-base", "--is-ancestor", recorded, "HEAD")


@pytest.mark.parametrize("action", ["apply", "finish"])
@pytest.mark.parametrize("ledger", ["delivery.json", "objectives.md"])
def test_mutating_entry_rechecks_ledger_after_prepare(python_exe, tmp_path, action, ledger):
    repo, remote, evidence = candidate(python_exe, tmp_path)
    path = repo / "changes/unreleased/1.3.0" / ledger
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("残缺账本\n")
    commit(repo)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    commits = git(repo, "rev-list", "v1.2.0..HEAD").stdout.split()
    evidence.write_text(json.dumps(proof(repo)))
    if action == "apply":
        result = apply(python_exe, repo, spec_file(tmp_path, repo, head, commits))
    else:
        result = call(python_exe, repo, "finish", "--yolo", "--evidence-file", str(evidence))
    assert error_of(result)["error"] == "invalid_delivery"
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == head
    assert not has_ref(remote, "refs/tags/v1.3.0")


def test_completed_planning_starts_a_new_historical_batch(python_exe, tmp_path):
    repo = repository(tmp_path, github=False)
    previous = "1.2.0"
    for version, name in (("1.3.0", "first"), ("1.4.0", "second")):
        released = change(repo, name)
        git(repo, "tag", f"v{version}")
        work = prepare(python_exe, repo, version)
        commits = git(repo, "rev-list", f"v{previous}..{released}").stdout.split()
        payload(apply(python_exe, work, spec_file(tmp_path, work, released, commits), version))
        evidence = tmp_path / "evidence.json"
        evidence.write_text(json.dumps(proof(work)))
        assert payload(call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence)))["result"]["completed"]
        assert (repo / f"changes/{version}/CHANGE.md").is_file()
        previous = version
