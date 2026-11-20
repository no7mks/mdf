"""support hotfix 真实收敛入口保持 Bug 真源只在 trunk。"""
from mdf_test_support import *  # noqa: F403
from support_github_flow import github_flow_repo, error_of
from support_delivery import commit
from support_release_flow import analyze_history


def prepare_hotfix(python_exe, tmp_path, *, slug=False, protected_link=False, pr=False):
    repo, remote = github_flow_repo(tmp_path, origin=True, pr=pr)
    if protected_link:
        prp = repo / "docs/proposals" / PRP_NAME
        prp.write_text(prp.read_text().replace("status: ready", "status: released\nreleased_in: 1.2.0"))
        bug = repo / "docs/bugs" / BUG_NAME
        bug.write_text(bug.read_text() + f"\n[已发布规划](../proposals/{PRP_NAME})\n")
        commit(repo)
    git(repo, "tag", "-a", "v1.2.0", "-m", "1.2.0 已发布")
    # tag 内保留 unrelated unreleased Bug，trunk 此后才登记本次 Bug。
    path = repo / "docs/bugs/bug-EF56-support-timeout.md"
    path.write_text((repo / "docs/bugs" / BUG_NAME).read_text().replace(BUG_ID, "bug-EF56"))
    commit(repo)
    git(repo, "push", "origin", "master", "--tags")
    name_args = ("--name", "support-timeout") if slug else ("--version", "1.2.1")
    started = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "hotfix",
                          *name_args, "--objectives-file", str(write_work_objectives(tmp_path))))
    work = Path(started["worktree"])
    seed_verify_branch(python_exe, work)
    from mdf_core.lifecycle.delivery_state import locate
    objective = locate(work)[0] / "objectives.md"
    before, after = objective.read_text().split("- [ ] catch-up", 1)
    objective.write_text(before.replace("[ ]", "[x]") + "- [ ] catch-up" + after)
    commit(work)
    analyze_history(work)
    sync = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    payload(mdf(python_exe, "catch-up", "--repo", str(work), "--complete", "--reviewed-head", sync["head"],
                "--summary", "同名远端增量验收通过"))
    change = {"fixed": ["bug-EF56"], "release_notes": {"Fixed": ["修复维护线超时"]},
              "body": "维护线修复已验收。", "evidence": {"tests": [], "commands": ["python -m pytest"], "artifacts": []},
              "trunk_fixes": [{"bug_id": "bug-EF56", "trunk_disposition": "urgent_support_first", "reason": "维护线紧急修复"}]}
    return repo, remote, work, change


def test_support_consolidate_keeps_bug_truth_on_trunk(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path)
    baseline = git(work, "rev-parse", "HEAD").stdout.strip()
    payload(mdf(python_exe, "consolidate", "--repo", str(work), "--release-date", "2026-11-21",
                "--hotfix-change-json", json.dumps(change)))
    assert git(work, "diff", baseline, "HEAD", "--", "docs/bugs").stdout == ""
    assert not (work / "docs/bugs/bug-EF56-support-timeout.md").exists()
    assert "status: open" in (work / "docs/bugs" / BUG_NAME).read_text()
    root = work / "changes/1.2.1/CHANGE.md"
    assert "bug-EF56" in root.read_text() and "trunk_fixes:" in root.read_text()
    git(work, "checkout", "--detach")
    payload(mdf(python_exe, "doctor", "--repo", str(work)))


def consolidate_hotfix(python_exe, work, change):
    return payload(mdf(python_exe, "consolidate", "--repo", str(work), "--release-date", "2026-11-21",
                       "--hotfix-change-json", json.dumps(change)))


def advance_trunk(repo, remote):
    old = git(repo, "rev-parse", "master").stdout.strip()
    path = repo / "docs/bugs/bug-EF56-support-timeout.md"
    path.write_text(path.read_text().replace("status: open", "status: fixed"))
    commit(repo)
    git(repo, "push", "origin", "master")
    return old


def test_merge_rechecks_remote_trunk_before_push(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path)
    consolidate_hotfix(python_exe, work, change)
    old = advance_trunk(repo, remote)
    # 本地 trunk 故意回到旧 open 记录；门禁必须看 origin。
    git(repo, "reset", "--hard", old)
    failed = mdf(python_exe, "merge", "--repo", str(work))
    assert error_of(failed)["error"] == "trunk_first_required"
    assert git(remote, "branch", "--list", "support/1.2").stdout == ""
    assert not git(remote, "tag", "--list", "v1.2.1").stdout.strip()


def test_published_support_retries_after_trunk_status_changes(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path)
    consolidate_hotfix(python_exe, work, change)
    merged = payload(mdf(python_exe, "merge", "--repo", str(work)))["merge_commit"]
    advance_trunk(repo, remote)
    payload(mdf(python_exe, "doctor", "--repo", str(work)))
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    args = ("--repo", str(repo), "--source", "hotfix/1.2.1")
    assert payload(mdf(python_exe, "publish", *args))["release_head"] == merged
    assert payload(mdf(python_exe, "publish", *args))["release_head"] == merged


def test_support_rejects_extra_fixed_closure_before_writes(python_exe, tmp_path):
    _repo, _remote, work, change = prepare_hotfix(python_exe, tmp_path)
    extra = [{"id": "bug-EF56", "resolution": "fixed", "fixed_in": "1.2.1"},
             {"id": BUG_ID, "resolution": "fixed", "fixed_in": "1.2.1"}]
    failed = mdf(python_exe, "consolidate", "--repo", str(work), "--release-date", "2026-11-21",
                 "--hotfix-change-json", json.dumps(change), "--closures-json", json.dumps(extra))
    assert error_of(failed)["error"] == "trunk_first_required"
    assert git(work, "status", "--porcelain").stdout == ""


def test_slug_hotfix_review_base_uses_published_tag(python_exe, tmp_path):
    _repo, _remote, work, change = prepare_hotfix(python_exe, tmp_path, slug=True)
    consolidate_hotfix(python_exe, work, change)
    merged = payload(mdf(python_exe, "merge", "--repo", str(work)))["merge_commit"]
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    published = payload(mdf(python_exe, "publish", "--repo", str(work), "--source", "hotfix/support-timeout"))
    from mdf_core.reviewing.context import context
    result = context(work, source="hotfix/support-timeout", head=merged, policy_ref=merged)
    assert result["delivery_base"] == published["release_head"]


@pytest.mark.parametrize("mutation", ["unknown", "duplicate", "unmatched", "wrong_identity"])
def test_detached_support_doctor_rejects_invalid_trunk_reference(python_exe, tmp_path, mutation):
    _repo, _remote, work, change = prepare_hotfix(python_exe, tmp_path)
    consolidate_hotfix(python_exe, work, change)
    root = work / "changes/1.2.1/CHANGE.md"
    text = root.read_text()
    if mutation == "unknown":
        root.write_text(text.replace("bug-EF56", "bug-GH78"))
    elif mutation == "duplicate":
        root.write_text(text.replace('  - bug_id: "bug-EF56"', '  - bug_id: "bug-EF56"\n    released_in: "1.2.1"\n  - bug_id: "bug-EF56"'))
    elif mutation == "unmatched":
        root.write_text(text.replace('bug_id: "bug-EF56"', 'bug_id: "bug-GH78"'))
    else:
        identity = work / "changes/1.2.1/delivery.json"
        data = json.loads(identity.read_text())
        data["base_branch"] = "master"
        identity.write_text(json.dumps(data))
    commit(work)
    git(work, "checkout", "--detach")
    from mdf_core.inspection.validate_records import validate_record_references
    findings = []
    validate_record_references(work, findings)
    assert any(item.code == "change.record_missing" for item in findings)


def test_support_rejects_rewrite_of_protected_bug_link(python_exe, tmp_path):
    _repo, _remote, work, change = prepare_hotfix(python_exe, tmp_path, protected_link=True)
    failed = mdf(python_exe, "consolidate", "--repo", str(work), "--release-date", "2026-11-21",
                 "--hotfix-change-json", json.dumps(change))
    assert error_of(failed)["error"] == "bug_source_forbidden"
    assert git(work, "status", "--porcelain").stdout == ""
    assert (work / "docs/proposals" / PRP_NAME).is_file()
    assert not (work / "changes/1.2.1").exists()
