"""无账本接管拒绝损坏账本、无证据发布与非法 hotfix。"""
import json

import pytest

from mdf_test_support import git, payload
from support_github_flow import error_of
from support_reconcile import repository, change, prepare, spec_file, apply, call, proof


@pytest.mark.parametrize("ledger", ["delivery.json", "objectives.md"])
def test_partial_ledger_never_downgrades(python_exe, tmp_path, ledger):
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "release/1.3.0")
    path = repo / "changes/unreleased/1.3.0" / ledger
    path.parent.mkdir(parents=True)
    path.write_text("损坏材料\n")
    assert error_of(call(python_exe, repo, "inspect"))["error"] == "invalid_delivery"


def test_record_only_does_not_publish_or_advance_objects(python_exe, tmp_path):
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "release/1.3.0")
    head = change(repo)
    work = prepare(python_exe, repo)
    before = {p: p.read_bytes() for p in (repo / "docs").rglob("*.md")}
    payload(apply(python_exe, work, spec_file(tmp_path, work, head)))
    assert "本记录不证明外部测试" in (work / "changes/1.3.0/CHANGE.md").read_text()
    assert payload(call(python_exe, work, "finish", "--record-only"))["result"]["completed"] is False
    assert {p: p.read_bytes() for p in before} == before
    assert error_of(call(python_exe, work, "finish", "--yolo"))["error"] == "external_evidence_required"
    assert "v1.3.0" not in git(work, "tag").stdout
    assert not list((work / "changes/1.3.0").rglob("delivery.json"))


@pytest.mark.parametrize("problem", ["stale", "missing-review", "failed"])
def test_external_evidence_binds_candidate_and_all_checks(python_exe, tmp_path, problem):
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "release/1.3.0")
    head = change(repo)
    work = prepare(python_exe, repo)
    payload(apply(python_exe, work, spec_file(tmp_path, work, head)))
    evidence = proof(work)
    if problem == "stale":
        change(work, "later")
    elif problem == "missing-review":
        evidence["checks"][0]["scope"].remove("code-review")
    else:
        evidence["checks"][0]["passed"] = False
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence))
    assert error_of(call(python_exe, work, "finish", "--yolo", "--evidence-file", str(path)))["error"] == "external_evidence_required"


def test_trunk_hotfix_is_rejected(python_exe, tmp_path):
    repo = repository(tmp_path)
    git(repo, "branch", "support/1.2", "v1.2.0")
    change(repo, "trunk_only")
    git(repo, "switch", "-c", "hotfix/1.2.1")
    change(repo)
    assert error_of(call(python_exe, repo, "inspect", "--support", "1.2"))["error"] == "invalid_release_line"


def test_record_only_keeps_open_bug_and_publish_requires_bug_close(python_exe, tmp_path):
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "release/1.3.0")
    head = change(repo)
    work = prepare(python_exe, repo)
    spec = spec_file(tmp_path, work, head)
    data = json.loads(spec.read_text())
    data["changes"][0]["fixed"] = ["bug-CD34"]
    spec.write_text(json.dumps(data))
    payload(apply(python_exe, work, spec))
    bug = work / "docs/bugs/bug-CD34-unreleased-timeout.md"
    assert "status: open" in bug.read_text()
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(proof(work)))
    failed = call(python_exe, work, "finish", "--yolo", "--evidence-file", str(evidence))
    assert error_of(failed)["error"] == "object_evidence_required"
    assert "status: open" in bug.read_text()


def test_no_tag_hotfix_has_no_new_route(python_exe, tmp_path):
    repo = repository(tmp_path)
    git(repo, "tag", "-d", "v1.2.0")
    git(repo, "switch", "-c", "hotfix/1.2.1")
    change(repo)
    assert error_of(call(python_exe, repo, "inspect"))["error"] == "missing_release_tag"


def test_record_only_refresh_appends_changes_and_noop_is_idempotent(python_exe, tmp_path):
    from mdf_core.foundation.yamlutil import read_frontmatter
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "release/1.3.0")
    head = change(repo)
    work = prepare(python_exe, repo)
    spec = spec_file(tmp_path, work, head)
    payload(apply(python_exe, work, spec))
    recorded = git(work, "rev-parse", "HEAD").stdout
    assert payload(apply(python_exe, work, spec))["result"]["already_recorded"]
    assert git(work, "rev-parse", "HEAD").stdout == recorded
    later = change(work, "later")
    commits = git(work, "rev-list", "v1.2.0..HEAD").stdout.split()
    spec = spec_file(tmp_path, work, later, commits)
    data = json.loads(spec.read_text())
    data["changes"][0]["release_notes"]["Changed"].append("追加的外部实现")
    spec.write_text(json.dumps(data))
    payload(apply(python_exe, work, spec))
    meta, _ = read_frontmatter(work / "changes/1.3.0/CHANGE.md")
    assert meta["release_notes"]["Changed"] == ["已核实的外部实现", "追加的外部实现"]
    assert (work / "CHANGELOG.md").read_text().count("## [1.3.0]") == 1
    assert not list((work / "changes").rglob("delivery.json"))


@pytest.mark.parametrize("github,branch", [(False, "hotfix/1.2.1"), (True, "release/1.3.0")])
def test_support_option_cannot_create_a_new_publication_route(python_exe, tmp_path, github, branch):
    repo = repository(tmp_path, github=github)
    git(repo, "branch", "support/1.2")
    git(repo, "switch", "-c", branch)
    change(repo)
    assert error_of(call(python_exe, repo, "inspect", "--support", "1.2"))["error"] == "invalid_support"


def test_already_merged_release_without_tag_routes_to_history(python_exe, tmp_path):
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "release/1.3.0")
    change(repo)
    git(repo, "switch", "master")
    git(repo, "merge", "--no-ff", "--no-edit", "release/1.3.0")
    merged = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "switch", "release/1.3.0")
    result = payload(call(python_exe, repo, "inspect"))["result"]
    assert result["record_mode"] == "post_hoc"
    assert result["releases"][0]["release_commit"] == merged
