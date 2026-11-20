"""PR mode 的 github-flow hotfix 在本地合入 support，并通过 push audit。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from support_github_flow import error_of
from support_sync import sync
from test_support_consolidate import prepare_hotfix, consolidate_hotfix


@pytest.mark.parametrize("existing,slug", [(False, False), (True, True)])
def test_support_hotfix_merges_locally_in_pr_mode(python_exe, tmp_path, existing, slug):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True, slug=slug)
    target = "support/1.2"
    source = git(work, "branch", "--show-current").stdout.strip()
    start = git(repo, "rev-parse", target).stdout.strip()
    trunk = git(repo, "rev-parse", "master").stdout.strip()
    if existing:
        git(repo, "push", "origin", target)
    consolidate_hotfix(python_exe, work, change)
    assert error_of(mdf(python_exe, "publish", "--repo", str(work)))["error"] == "closeout_required"
    assert "- [ ] publish" not in (work / "changes/1.2.1/objectives.md").read_text()
    route = payload(mdf(python_exe, "delivery", "route", "--repo", str(work)))["result"]
    assert route["next"] == "merge"
    assert error_of(mdf(python_exe, "pr", "--repo", str(work)))["error"] == "invalid_closeout"
    assert error_of(mdf(python_exe, "pr-watch", "--repo", str(work)))["error"] == "invalid_closeout"
    integrated = payload(mdf(python_exe, "incremental-integration", "--repo", str(work)))
    assert integrated["completed"] and integrated["target_head"] == start
    assert git(remote, "branch", "--list", target).stdout.strip() == (target if existing else "")

    head = git(work, "rev-parse", "HEAD").stdout.strip()
    merged = payload(mdf(python_exe, "merge", "--repo", str(work)))["merge_commit"]
    assert git(remote, "rev-parse", target).stdout.strip() == merged
    assert git(repo, "show", "-s", "--format=%P", merged).stdout.split() == [start, head]
    assert git(remote, "rev-parse", "master").stdout.strip() == trunk
    assert git(remote, "tag", "--list", "v1.2.1").stdout == ""
    assert error_of(mdf(python_exe, "publish", "--repo", str(work)))["error"] == "closeout_required"

    before = start if existing else "0" * 40
    audit = payload(mdf(python_exe, "audit-push", "--repo", str(repo), "--branch", target,
                        "--before", before, "--after", merged, "--collect-evidence"))["result"]
    assert audit["verdict"] == "pass" and audit["policy_ref"] == start
    assert [item["reason"] for item in audit["commits"]] == ["local_support_merge"]
    route = payload(mdf(python_exe, "delivery", "route", "--repo", str(work)))["result"]
    assert route["next"] == "close-out"
    closed = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert closed["next_intent"] == "publish" and closed["version"] == "1.2.1"
    assert git(remote, "branch", "--list", source).stdout == ""
    assert git(remote, "tag", "--list", "v1.2.1").stdout == ""
    assert git(remote, "show", f"{target}:changes/1.2.1/CHANGE.md").stdout
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", source))
    git(repo, "worktree", "remove", str(work))
    recovery = ("--repo", str(repo), "--source", source, "--version", "1.2.1")
    assert payload(mdf(python_exe, "delivery", "route", *recovery))["result"]["next"] == "publish"
    if existing:
        support = tmp_path / "updated-support"
        git(repo, "worktree", "add", str(support), target)
        git(support, "commit", "--allow-empty", "-m", "test: 模拟维护线继续前进")
        git(support, "push", "origin", target)
        assert git(remote, "rev-parse", target).stdout.strip() != merged
    published = payload(mdf(python_exe, "publish", *recovery))
    assert published["release_head"] == merged
    assert git(remote, "rev-parse", "v1.2.1^{commit}").stdout.strip() == merged
    assert payload(mdf(python_exe, "publish", *recovery))["release_head"] == merged
    assert payload(mdf(python_exe, "delivery", "route", *recovery))["result"]["state"] == "completed"


def test_new_remote_support_tip_requires_sync_and_incremental_acceptance(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    target = "support/1.2"
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "incremental-integration", "--repo", str(work)))
    other = tmp_path / "other-support"
    git(repo, "worktree", "add", "--detach", str(other), target)
    (other / "src/remote_fix.py").write_text("fixed = True\n")
    commit(other)
    remote_head = git(other, "rev-parse", "HEAD").stdout.strip()
    git(other, "push", "origin", f"HEAD:refs/heads/{target}")

    def merge():
        return mdf(python_exe, "merge", "--repo", str(work))

    assert error_of(merge())["error"] == "publish_state_changed"
    assert git(remote, "rev-parse", target).stdout.strip() == remote_head
    assert payload(sync(python_exe, repo, pr=False))["trunks"][target]["pull"] == "ff"
    assert error_of(merge())["error"] == "integration_required"
    assert (work / "src/remote_fix.py").is_file()
    payload(mdf(python_exe, "consolidate", "--repo", str(work), "--incremental"))
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    payload(mdf(python_exe, "incremental-integration", "--repo", str(work), "--complete",
                "--reviewed-head", head, "--summary", "验收远端维护线增量"))
    merged = payload(merge())["merge_commit"]
    assert git(remote, "show", "-s", "--format=%P", merged).stdout.split() == [remote_head, head]


def test_support_hotfix_merge_requires_acceptance(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    target = "support/1.2"
    source = git(work, "branch", "--show-current").stdout.strip()
    consolidate_hotfix(python_exe, work, change)
    git(repo, "push", "origin", target)
    base = git(remote, "rev-parse", target).stdout.strip()
    support = tmp_path / "support-owner"
    git(repo, "worktree", "add", str(support), target)
    blocked = mdf(python_exe, "merge-no-ff", "--repo", str(support), "--commit", source)
    assert error_of(blocked)["error"] == "delivery_merge_required"

    git(support, "merge", "--no-ff", "--no-edit", source)
    blocked = mdf(python_exe, "merge", "--repo", str(work))
    assert error_of(blocked)["error"] == "integration_required"
    for pr in (False, True):
        assert error_of(sync(python_exe, repo, pr=pr))["error"] == "delivery_merge_required"
        assert git(remote, "rev-parse", target).stdout.strip() == base


def test_workflow_switch_waits_for_support_hotfix_publication(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    git(repo, "worktree", "remove", str(work))
    git(repo, "branch", "develop", "master")
    switch = ("workflow", "switch", "--repo", str(repo), "--model", "gitflow")
    assert error_of(mdf(python_exe, *switch))["error"] == "workflow_not_idle"
    assert git(remote, "tag", "--list", "v1.2.1").stdout == ""
    source = "hotfix/1.2.1"
    args = ("--repo", str(repo), "--source", source)
    published = payload(mdf(python_exe, "publish", *args))
    from mdf_core.lifecycle.delivery_state import read_json, write_json
    from mdf_core.lifecycle.publish import merge_record_path
    receipt = merge_record_path(repo, source, "1.2.1")
    data = read_json(receipt)
    del data["published"]
    write_json(receipt, data)
    assert payload(mdf(python_exe, "delivery", "route", *args))["result"]["next"] == "publish"
    assert error_of(mdf(python_exe, *switch))["error"] == "workflow_not_idle"
    resumed = payload(mdf(python_exe, "publish", *args))
    assert resumed["release_head"] == published["release_head"] and resumed["tag"] == published["tag"]
    assert payload(mdf(python_exe, *switch))["to"]["model"] == "gitflow"
