"""PR mode 的 github-flow hotfix 在本地合入 support，并通过 push audit。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from support_github_flow import error_of
from support_sync import sync
from test_support_consolidate import prepare_hotfix, consolidate_hotfix


@pytest.mark.parametrize("existing,slug", [(False, False), (True, True)])
def test_support_hotfix_merges_locally_in_pr_mode(python_exe, tmp_path, monkeypatch, existing, slug):
    from support_pull import Platform, squash_pending
    from mdf_core.lifecycle import pull_finish
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True, slug=slug)
    source = git(work, "branch", "--show-current").stdout.strip()
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    monkeypatch.setattr(pull_finish, "origin", lambda *_: {})
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    if existing:
        git(repo, "push", "origin", "support/1.2")
    consolidate_hotfix(python_exe, work, change)
    assert error_of(mdf(python_exe, "publish", "--repo", str(work)))["error"] == "merge_required"
    payload(mdf(python_exe, "incremental-integration", "--repo", str(work)))
    merged = payload(mdf(python_exe, "merge", "--repo", str(work)))["merge_commit"]
    assert payload(mdf(python_exe, "delivery", "route", "--repo", str(work)))["result"]["next"] == "publish"
    assert error_of(mdf(python_exe, "finish-gitflow", "--repo", str(work)))["error"] == "release_not_published"
    published = payload(mdf(python_exe, "publish", "--repo", str(work)))
    assert published["release_head"] == merged and published["next_intent"] == "sync-changelog"
    assert error_of(mdf(python_exe, "finish-gitflow", "--repo", str(work)))["error"] == "changelog_sync_required"
    args = ("--repo", str(work), "--source", source, "--version", "1.2.1")
    prepared = payload(mdf(python_exe, "sync-changelog", *args))
    pm_work = Path(prepared["worktree"])
    assert payload(mdf(python_exe, "sync-changelog", *args)) == prepared
    assert git(work, "branch", "--show-current").stdout.strip() == source
    assert git(repo, "branch", "--show-current").stdout.strip() == "master"
    assert (pm_work / ".mdf/manifest.yaml").read_text() == (repo / ".mdf/manifest.yaml").read_text()
    payload(mdf(python_exe, "doctor", "--repo", str(pm_work)))
    squash_pending(pm_work)
    payload(mdf(python_exe, "pr", "--repo", str(pm_work)))
    payload(mdf(python_exe, "pr", "--repo", str(pm_work)))
    assert len(platform.pulls) == 1
    assert error_of(mdf(python_exe, "sync-changelog", *args, "--complete"))["error"] == "pr_not_merged"
    if existing:
        (repo / "main-only.txt").write_text("同步 PR 创建后的主线增量\n")
        commit(repo)
        git(repo, "push", "origin", "master")
    platform.merge(1, tmp_path)
    payload(mdf(python_exe, "pr", "--repo", str(pm_work)))
    before = git(repo, "rev-parse", f"{platform.pulls[0]['merge_commit']}^1").stdout.strip()
    evidence = tmp_path / "pm-evidence.json"
    evidence.write_text(json.dumps({"pull_requests": platform.pulls}))
    audit = payload(mdf(python_exe, "audit-push", "--repo", str(repo), "--branch", "master",
                        "--before", before, "--after", platform.pulls[0]["merge_commit"],
                        "--evidence-file", str(evidence)))["result"]
    assert audit["verdict"] == "pass"
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(pm_work)))
    git(repo, "worktree", "remove", str(pm_work))
    payload(mdf(python_exe, "sync-changelog", *args, "--complete"))
    assert payload(mdf(python_exe, "delivery", "route", *args))["result"]["next"] == "close-out"
    assert "1.2.1" in (repo / "CHANGELOG.md").read_text()
    assert git(repo, "diff", merged, "master", "--", "changes/1.2.1").stdout == ""
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    git(repo, "worktree", "remove", str(work))
    recovery = ("--repo", str(repo), "--source", source, "--version", "1.2.1")
    assert payload(mdf(python_exe, "delivery", "route", *recovery))["result"]["state"] == "completed"
    assert payload(mdf(python_exe, "publish", *recovery))["release_head"] == merged


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
    git(repo, "branch", "develop", "master")
    switch = ("workflow", "switch", "--repo", str(repo), "--model", "gitflow")
    assert error_of(mdf(python_exe, *switch))["error"] == "workflow_not_idle"
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
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    git(repo, "worktree", "remove", str(work))
    assert payload(mdf(python_exe, *switch))["to"]["model"] == "gitflow"


@pytest.mark.parametrize("mutation", ["code", "other-version", "other-note"])
def test_sync_pr_rejects_unrelated_changes(python_exe, tmp_path, mutation):
    from mdf_core.workspace.pm import require_pm_diff
    from mdf_core.foundation.errors import MDFError
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    prepared = payload(mdf(python_exe, "sync-changelog", "--repo", str(work)))
    pm_work = Path(prepared["worktree"])
    published = git(remote, "rev-parse", "v1.2.1").stdout
    if mutation == "other-note":
        path = pm_work / "CHANGELOG.md"
        path.write_text(path.read_text().replace("# Changelog", "# Changelog\n\n无关说明"))
    else:
        path = pm_work / ("src/unrelated.py" if mutation == "code" else "changes/9.9.9/CHANGE.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("unrelated = True\n")
    commit(pm_work)
    if mutation == "code":
        git(pm_work, "revert", "--no-edit", "HEAD")
    with pytest.raises(MDFError) as exc:
        require_pm_diff(pm_work, "origin/master", "HEAD", prepared["source"])
    assert exc.value.code == "pm_paths_forbidden"
    assert git(remote, "rev-parse", "v1.2.1").stdout == published
    assert git(work, "branch", "--show-current").stdout.strip() == "hotfix/1.2.1"


def test_support_publish_preserves_unmerged_source_changes(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    (work / "src/later.py").write_text("later = True\n")
    commit(work)
    result = mdf(python_exe, "publish", "--repo", str(work))
    assert error_of(result)["error"] == "pull_state_changed"
    assert git(remote, "tag", "--list", "v1.2.1").stdout == ""
    assert (work / "src/later.py").read_text() == "later = True\n"
