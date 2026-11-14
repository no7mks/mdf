"""github-flow 的 PR mode：trunk 为目标、无 develop 回合、tag 固定 release_head，以及短命 planning。"""
from __future__ import annotations
import json
from mdf_test_support import *  # noqa: F403
from support_delivery import write_changelog_release
from support_github_flow import commit, error_of, github_flow_repo, has_ref
from support_planning import add_prp
from support_pull import Platform, squash_pending


def pr_repo(tmp_path, monkeypatch):
    repo, remote = github_flow_repo(tmp_path, origin=True, pr=True)
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    from mdf_core.lifecycle import pull_finish
    identity = {"provider": "github", "host": "forge.invalid", "project": "team/project", "origin": str(remote)}
    monkeypatch.setattr(pull_finish, "origin", lambda *_: identity)
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    return repo, remote, platform


def test_entries_are_split_by_workflow(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path)
    assert error_of(mdf(python_exe, "dev-pr", "--repo", str(repo)))["error"] == "github_flow_unsupported"
    assert error_of(mdf(python_exe, "to", "--repo", str(repo), "--target", "develop"))["error"] == "github_flow_unsupported"
    gitflow = copy_fixture(tmp_path / "gf")
    init_git(gitflow)
    assert error_of(mdf(python_exe, "trunk-pr", "--repo", str(gitflow)))["error"] == "gitflow_required"


def test_trunk_pr_requires_pr_mode(python_exe, tmp_path):
    repo, _ = github_flow_repo(tmp_path, origin=True)
    (repo / "local.txt").write_text("trunk 本地增量\n")
    commit(repo)
    assert error_of(mdf(python_exe, "trunk-pr", "--repo", str(repo)))["error"] == "pr_mode_required"


def test_trunk_pr_moves_local_trunk_work_to_adhoc(python_exe, tmp_path, monkeypatch):
    repo, remote, _ = pr_repo(tmp_path, monkeypatch)
    before = git(repo, "rev-parse", "master").stdout.strip()
    (repo / "local.txt").write_text("trunk 本地增量\n")
    commit(repo)
    kept = git(repo, "rev-parse", "master").stdout.strip()
    result = payload(mdf(python_exe, "trunk-pr", "--repo", str(repo), "--slug", "trunk-work"))["result"]
    assert result["source"] == "adhoc/trunk-work" and result["next_intent"] == "trunk-pr"
    assert git(repo, "rev-parse", "master").stdout.strip() == before
    assert git(repo, "rev-parse", "adhoc/trunk-work").stdout.strip() == kept


def test_release_pr_tags_release_head_and_never_backmerges(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = pr_repo(tmp_path, monkeypatch)
    git(repo, "tag", "-a", "v1.2.0", "-m", "test: v1.2.0")
    git(repo, "push", "origin", "--tags")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "release", "--version", "1.3.0",
                       "--objectives-file", str(write_release_objectives(tmp_path))))
    work = Path(data["worktree"])
    write_changelog_release(work, "1.3.0")
    commit(work)
    squash_pending(work)
    first = payload(mdf(python_exe, "pr", "--repo", str(work)))
    assert first["status"] == "waiting_for_merge" and first["source"] == "release/1.3.0"
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    merged = platform.merge(1, tmp_path)
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", "release/1.3.0"))
    assert done["completed"] and done["targets"] == ["master"] and done["backmerge"] is None
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == head != merged
    assert not has_ref(repo, "refs/heads/develop") and not has_ref(remote, "refs/heads/develop")
    git(remote, "merge-base", "--is-ancestor", head, "master")


def test_planning_pr_is_short_lived_and_blocks_dependent_start(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = pr_repo(tmp_path, monkeypatch)
    ensured = payload(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))
    plan = Path(ensured["worktree"])
    assert ensured["branch"] == "planning" and ensured["created"]
    assert git(plan, "rev-parse", "HEAD").stdout == git(repo, "rev-parse", "origin/master").stdout
    add_prp(plan, "prp-0002")
    commit(plan, "docs(planning): 新增 prp-0002")
    blocked = mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature", "--proposal", "prp-0002",
                  "--objectives-file", str(write_work_objectives(tmp_path)), "--roster", "solo")
    assert error_of(blocked)["error"] == "planning_pr_pending"
    assert error_of(mdf(python_exe, "planning", "land", "--repo", str(repo)))["error"] == "planning_pr_required"
    squash_pending(plan)
    assert payload(mdf(python_exe, "pr", "--repo", str(plan)))["status"] == "waiting_for_merge"
    platform.merge(1, tmp_path)
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", "planning"))
    assert done["completed"] and done["targets"] == ["master"]
    assert not has_ref(repo, "refs/heads/planning") and not has_ref(remote, "refs/heads/planning")
    assert (repo / "docs/proposals").exists()
    again = payload(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))
    assert again["branch"] == "planning" and git(Path(again["worktree"]), "branch", "--show-current").stdout.strip() == "planning"
    assert payload(mdf(python_exe, "planning", "land", "--repo", str(repo)))["landed"] is False


def test_local_planning_uses_clean_trunk_worktree(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path)
    ensured = payload(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))
    assert ensured["branch"] == "master" and Path(ensured["worktree"]).resolve() == repo.resolve()
    assert not has_ref(repo, "refs/heads/planning")
    assert payload(mdf(python_exe, "planning", "land", "--repo", str(repo)))["landed"] is False
    (repo / "dirty.txt").write_text("未提交\n")
    git(repo, "add", "dirty.txt")
    assert error_of(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))["error"] == "dirty_worktree"


def _audit(python_exe, repo, branch, before, after, proof=None):
    args = ["audit-push", "--repo", str(repo), "--branch", branch, "--before", before, "--after", after]
    if proof is not None:
        path = repo.parent / "proof.json"
        path.write_text(json.dumps(proof))
        args += ["--evidence-file", str(path)]
    return mdf(python_exe, *args)


def test_audit_push_covers_custom_trunk_and_forbids_support_merge(python_exe, tmp_path):
    repo, _remote = github_flow_repo(tmp_path, trunk="main", origin=True, pr=True)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    assert error_of(_audit(python_exe, repo, "develop", base, base))["error"] == "invalid_audit_target"
    (repo / "src/service.py").write_text("direct = True\n")
    commit(repo)
    direct = payload(_audit(python_exe, repo, "main", base, "HEAD"))["result"]
    assert direct["verdict"] == "violation" and direct["commits"][0]["reason"] == "direct_trunk_commit"
    git(repo, "reset", "--hard", base)
    git(repo, "checkout", "-b", "support/1.2", base)
    (repo / "support.txt").write_text("support = True\n")
    commit(repo)
    support = payload(_audit(python_exe, repo, "support/1.2", base, "HEAD"))["result"]
    assert support["verdict"] == "violation"
    git(repo, "checkout", "-b", "feature/x", base)
    (repo / "src/service.py").write_text("feature = True\n")
    commit(repo)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "main")
    git(repo, "merge", "--no-ff", "--no-edit", "feature/x")
    merged = git(repo, "rev-parse", "HEAD").stdout.strip()
    proof = {"pull_requests": [{"id": 1, "url": "https://forge.invalid/pull/1", "state": "merged",
                                "source": "feature/x", "target": "main", "head": head, "merge_commit": merged}]}
    accepted = payload(_audit(python_exe, repo, "main", base, merged, proof))["result"]
    assert accepted["verdict"] == "pass" and accepted["commits"][0]["reason"] == "platform_merge"
    git(repo, "merge", "--no-ff", "--no-edit", "support/1.2")
    forbidden_merge = git(repo, "rev-parse", "HEAD").stdout.strip()
    support_head = git(repo, "rev-parse", "support/1.2").stdout.strip()
    bad = {"pull_requests": [{"id": 2, "url": "https://forge.invalid/pull/2", "state": "merged",
                              "source": "support/1.2", "target": "main", "head": support_head,
                              "merge_commit": forbidden_merge}]}
    rejected = payload(_audit(python_exe, repo, "main", merged, forbidden_merge, bad))["result"]
    assert rejected["verdict"] == "violation" and rejected["commits"][0]["reason"] == "support_merge_forbidden"


def test_github_flow_sync_reports_trunk_pr_and_aligns_shared_support(python_exe, tmp_path):
    repo, remote = github_flow_repo(tmp_path, trunk="main", origin=True, pr=True)
    git(repo, "branch", "support/1.2")
    git(repo, "push", "-u", "origin", "support/1.2")
    clone = tmp_path / "other"
    git(tmp_path, "clone", "--branch", "support/1.2", str(remote), str(clone))
    (clone / "support.txt").write_text("远端维护\n")
    commit(clone, "fix: 远端维护线")
    git(clone, "push", "origin", "support/1.2")
    behind = payload(mdf(python_exe, "sync", "--repo", str(repo)))
    assert behind["branches"]["support/1.2"]["relation"] == "behind"
    assert "main" not in behind["pull_plan"]
    aligned = payload(mdf(python_exe, "sync", "--repo", str(repo), "--confirm", behind["confirmation"]))
    assert aligned["trunks"]["support/1.2"]["pull"] == "ff"
    assert git(repo, "rev-parse", "support/1.2").stdout == git(remote, "rev-parse", "support/1.2").stdout
    (repo / "src/service.py").write_text("ahead = True\n")
    commit(repo, "feat: trunk 领先")
    ahead = payload(mdf(python_exe, "sync", "--repo", str(repo)))
    assert ahead["pull_plan"]["main"]["action"] == "trunk_pr"


def test_support_branch_can_never_merge_into_trunk(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path)
    git(repo, "branch", "support/1.2")
    failed = mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", "support/1.2")
    assert error_of(failed)["error"] == "support_to_trunk_forbidden"


def test_conflicting_release_goes_through_integration_branch_and_tags_release_head(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = pr_repo(tmp_path, monkeypatch)
    git(repo, "tag", "-a", "v1.2.0", "-m", "test: v1.2.0")
    git(repo, "push", "origin", "--tags")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "release", "--version", "1.3.0",
                       "--objectives-file", str(write_release_objectives(tmp_path))))
    work = Path(data["worktree"])
    write_changelog_release(work, "1.3.0")
    (work / "src/service.py").write_text("released = True\n")
    commit(work)
    squash_pending(work)
    release_head = git(work, "rev-parse", "HEAD").stdout.strip()
    (repo / "src/service.py").write_text("trunk_work = True\n")
    commit(repo, "fix: trunk 上的并行修改")
    git(repo, "push", "origin", "master")
    blocked = mdf(python_exe, "pr", "--repo", str(work))
    assert error_of(blocked)["error"] == "integration_required"
    conflict = mdf(python_exe, "release-integrate", "--repo", str(work))
    info = error_of(conflict)
    assert info["error"] == "merge_conflict" and info["details"]["conflicts"] == ["src/service.py"]
    integ = Path(info["details"]["worktree"])
    (integ / "src/service.py").write_text("trunk_work = True\nreleased = True\n")
    git(integ, "add", "src/service.py")
    git(integ, "commit", "-m", "chore(release): 解决 trunk 冲突")
    squash_pending(integ)
    assert payload(mdf(python_exe, "release-integrate", "--repo", str(work)))["status"] == "up_to_date"
    first = payload(mdf(python_exe, "pr", "--repo", str(integ)))
    assert first["status"] == "waiting_for_merge" and first["source"] == "codex/integrate/release-1.3.0"
    platform.merge(1, tmp_path)
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", first["source"]))
    assert done["completed"] and done["tag"] == "v1.3.0"
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == release_head
    git(remote, "merge-base", "--is-ancestor", release_head, "master")
