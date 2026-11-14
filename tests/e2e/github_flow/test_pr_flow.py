"""github-flow 的 PR mode：trunk 为目标、无 develop 回合、tag 固定 release_head，以及独立 pm 分支。"""
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


def pm_commit(python_exe, repo, slug="create-prp"):
    return mdf(python_exe, "pm", "commit", "--repo", str(repo), "--slug", slug,
               "--message", "docs(pm): 更新项目记录")


def test_pm_pr_uses_trunk_worktree_and_blocks_dependent_start(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = pr_repo(tmp_path, monkeypatch)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    trees = git(repo, "worktree", "list", "--porcelain").stdout
    prepared = payload(mdf(python_exe, "pm", "prepare", "--repo", str(repo)))
    assert prepared["branch"] == "master" and Path(prepared["worktree"]).resolve() == repo.resolve()
    add_prp(repo, "prp-0002")
    git(repo, "add", "docs/proposals")
    result = payload(pm_commit(python_exe, repo))
    source = result["source"]
    assert source.startswith("pm/create-prp-")
    assert git(repo, "worktree", "list", "--porcelain").stdout == trees
    assert git(repo, "rev-parse", f"{source}^").stdout.strip() == head
    assert not has_ref(repo, "refs/heads/planning")
    blocked = mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature", "--proposal", "prp-0002",
                  "--objectives-file", str(write_work_objectives(tmp_path)), "--roster", "solo")
    assert error_of(blocked)["error"] == "pm_pr_pending"
    assert error_of(mdf(python_exe, "to", "--repo", str(repo), "--target", source))["error"] == "unsupported_branch"
    git(repo, "switch", source)
    (repo / "docs/context").mkdir(exist_ok=True)
    (repo / "docs/context/notes.md").write_text("补充项目背景\n")
    commit(repo, "docs(pm): 补充背景")
    git(repo, "switch", "master")
    request = ["pr", "--repo", str(repo), "--source", source]
    assert error_of(mdf(python_exe, *request))["error"] == "squash_required"
    git(repo, "switch", source)
    squash_pending(repo)
    git(repo, "switch", "master")
    assert payload(mdf(python_exe, *request))["status"] == "waiting_for_merge"
    git(repo, "switch", source)
    (repo / "docs/context/notes.md").write_text("修订项目背景\n")
    commit(repo, "docs(pm): 修订背景")
    git(repo, "switch", "master")
    updated = payload(mdf(python_exe, "pr", "--repo", str(repo), "--source", source))
    assert updated["pull_request"]["id"] == 1
    merged = platform.merge(1, tmp_path)
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", source))
    audit = payload(_audit(python_exe, repo, "master", head, merged,
                           {"pull_requests": [done["pull_request"]]}))["result"]
    assert audit["verdict"] == "pass"
    assert done["completed"] and done["targets"] == ["master"]
    assert not has_ref(repo, f"refs/heads/{source}") and not has_ref(remote, f"refs/heads/{source}")
    assert git(repo, "branch", "--show-current").stdout.strip() == "master"
    assert list((repo / "docs/proposals").glob("prp-0002-*"))

    add_prp(repo, "prp-0003")
    git(repo, "add", "docs/proposals")
    assert payload(pm_commit(python_exe, repo))["source"] != source


def test_pm_local_commits_directly_on_custom_trunk(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path, trunk="main")
    prepared = payload(mdf(python_exe, "pm", "prepare", "--repo", str(repo)))
    assert prepared["branch"] == "main" and Path(prepared["worktree"]).resolve() == repo.resolve()
    assert error_of(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))["error"] == "github_flow_unsupported"
    assert error_of(mdf(python_exe, "to", "--repo", str(repo), "--target", "plan"))["error"] == "github_flow_unsupported"
    assert payload(mdf(python_exe, "make-id", "--repo", str(repo), "--type", "proposal", "--slug", "example"))["id"]
    add_prp(repo, "prp-0002")
    git(repo, "add", "docs/proposals")
    assert error_of(mdf(python_exe, "pm", "prepare", "--repo", str(repo)))["error"] == "dirty_worktree"
    result = payload(pm_commit(python_exe, repo))
    assert result["source"] == "main"
    assert result["head"] == git(repo, "rev-parse", "main").stdout.strip()
    assert not git(repo, "branch", "--list", "planning", "pm/*").stdout.strip()


def test_pm_rejects_unrelated_staged_paths_and_preserves_index(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path)
    add_prp(repo, "prp-0002")
    (repo / "docs" / "outside.md").write_text("无关内容\n")
    git(repo, "add", "docs")
    before = git(repo, "diff", "--cached", "--name-only").stdout
    error = error_of(pm_commit(python_exe, repo))
    assert error["error"] == "pm_paths_forbidden" and error["details"]["paths"] == ["docs/outside.md"]
    assert git(repo, "diff", "--cached", "--name-only").stdout == before


def test_pm_pr_rejects_outside_history_even_if_reverted(python_exe, tmp_path, monkeypatch):
    repo, remote, _ = pr_repo(tmp_path, monkeypatch)
    add_prp(repo, "prp-0002")
    git(repo, "add", "docs/proposals")
    source = payload(pm_commit(python_exe, repo))["source"]
    git(repo, "switch", source)
    (repo / "outside.py").write_text("value = 1\n")
    commit(repo, "chore: 添加非项目记录路径")
    git(repo, "revert", "--no-edit", "HEAD")
    from mdf_core.foundation.errors import MDFError
    from mdf_core.workspace.squash import check
    with pytest.raises(MDFError) as forbidden:
        check(repo)
    assert forbidden.value.code == "pm_paths_forbidden"
    git(repo, "switch", "master")
    result = mdf(python_exe, "pr", "--repo", str(repo), "--source", source)
    assert error_of(result)["error"] == "pm_paths_forbidden"
    assert not has_ref(remote, f"refs/heads/{source}")


def test_concurrent_pm_commit_cannot_switch_or_consume_index(python_exe, tmp_path, monkeypatch):
    import subprocess

    from mdf_core.workspace import pm

    repo, _ = github_flow_repo(tmp_path, origin=True, pr=True)
    add_prp(repo, "prp-0002")
    git(repo, "add", "docs/proposals")
    trunk = git(repo, "rev-parse", "master").stdout.strip()
    script = skill_dir("mdf") / "scripts/mdf.py"
    real_git = pm.git
    concurrent = []

    def interleave(path, *args, **kwargs):
        if args[:2] == ("switch", "-c"):
            concurrent.append(subprocess.run(
                [python_exe, str(script), "pm", "commit", "--repo", str(repo),
                 "--slug", "concurrent", "--message", "docs(pm): 并发提交"],
                capture_output=True, text=True, check=False,
            ))
        return real_git(path, *args, **kwargs)

    monkeypatch.setattr(pm, "git", interleave)
    result = payload(pm_commit(python_exe, repo))
    assert len(concurrent) == 1 and error_of(concurrent[0])["error"] == "finish_busy"
    assert git(repo, "rev-parse", result["source"]).stdout.strip() == result["head"]
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == trunk
    assert git(repo, "branch", "--list", "pm/*", "--format=%(refname:short)").stdout.split() == [result["source"]]


def test_pm_proposal_feedback_can_reformat_and_update_same_pr(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = pr_repo(tmp_path, monkeypatch)
    proposal = add_prp(repo, "prp-0002")
    git(repo, "add", str(proposal))
    initial = payload(pm_commit(python_exe, repo))
    source = initial["source"]
    args = ["--repo", str(repo), "--source", source]
    first = payload(mdf(python_exe, "pr", *args))
    git(repo, "switch", source)
    format_args = ["--repo", str(repo), "--proposal", "prp-0002"]
    draft = repo / payload(mdf(python_exe, "prp-format", "draft", *format_args))["path"]
    draft.write_text(draft.read_text() + "\n## 评审补充\n\n明确校验范围。\n")
    payload(mdf(python_exe, "prp-format", "preview", *format_args))
    payload(mdf(python_exe, "prp-format", "ready", *format_args, "--confirmed"))
    outside = repo / "docs/outside.md"
    outside.write_text("无关记录\n")
    git(repo, "add", "docs")
    assert error_of(pm_commit(python_exe, repo))["error"] == "pm_paths_forbidden"
    git(repo, "restore", "--staged", str(outside))
    outside.unlink()
    revised = payload(pm_commit(python_exe, repo))
    assert revised["source"] == source and revised["head"] != initial["head"]
    assert git(repo, "branch", "--show-current").stdout.strip() == "master"
    updated = payload(mdf(python_exe, "pr", *args))
    assert updated["pull_request"]["id"] == first["pull_request"]["id"]
    assert git(remote, "rev-parse", source).stdout.strip() == revised["head"]
    platform.merge(1, tmp_path)
    assert payload(mdf(python_exe, "finish-gitflow", *args))["completed"]
    assert "明确校验范围" in proposal.read_text()


@pytest.mark.parametrize("status", ["draft", "ready"])
def test_linked_proposal_routes_to_ordinary_delivery_before_conversion(python_exe, tmp_path, status):
    repo = github_flow_repo(tmp_path, trunk="main")
    proposal = add_prp(repo, "prp-0002", status=status)
    index = repo / "docs/README.md"
    index.write_text(index.read_text() + f"\n[计划](proposals/{proposal.name})\n")
    commit(repo)
    args = ["--repo", str(repo), "--proposal", "prp-0002"]
    plan = payload(mdf(python_exe, "prp-format", "plan", *args))
    assert plan["outside_pm"] == ["docs/README.md"]
    assert git(repo, "status", "--porcelain").stdout == ""
    action = "ready" if status == "draft" else "draft"
    assert error_of(mdf(python_exe, "prp-format", action, *args))["error"] == "proposal_requires_delivery"
    assert git(repo, "status", "--porcelain").stdout == ""
    owner = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "adhoc",
                        "--name", "review-linked-proposal", "--work", "评审 Proposal 并同步外部引用"))
    work = Path(owner["worktree"])
    work_args = ["--repo", str(work), "--proposal", "prp-0002"]
    if status == "ready":
        payload(mdf(python_exe, "prp-format", "draft", *work_args))
    payload(mdf(python_exe, "prp-format", "preview", *work_args))
    result = payload(mdf(python_exe, "prp-format", "ready", *work_args, "--confirmed"))
    assert (work / result["path"]).is_file()
    assert f"proposals/{proposal.with_suffix('.html').name}" in (work / "docs/README.md").read_text()
    assert proposal.is_file()
    assert git(repo, "status", "--porcelain").stdout == ""
    assert not git(repo, "branch", "--list", "pm/*").stdout


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
    proof["pull_requests"][0]["source"] = "pm/not-records"
    rejected_pm = payload(_audit(python_exe, repo, "main", base, merged, proof))["result"]
    assert rejected_pm["verdict"] == "violation"
    assert rejected_pm["commits"][0]["reason"] == "pm_paths_forbidden"
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


def test_release_head_updates_before_pr_and_locks_after(python_exe, tmp_path, monkeypatch):
    repo, _remote, _platform = pr_repo(tmp_path, monkeypatch)
    git(repo, "tag", "-a", "v1.2.0", "-m", "test: v1.2.0")
    git(repo, "push", "origin", "--tags")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "release", "--version", "1.3.0",
                       "--objectives-file", str(write_release_objectives(tmp_path))))
    work = Path(data["worktree"])
    write_changelog_release(work, "1.3.0")
    commit(work)
    first = payload(mdf(python_exe, "release-integrate", "--repo", str(work)))
    assert first["release_head"] == git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "extra.txt").write_text("追加\n")
    commit(work)
    new_head = git(work, "rev-parse", "HEAD").stdout.strip()
    second = payload(mdf(python_exe, "release-integrate", "--repo", str(work)))
    assert second["release_head"] == new_head
    integ = Path(second["worktree"])
    git(integ, "merge-base", "--is-ancestor", new_head, "HEAD")
    squash_pending(integ)
    opened = payload(mdf(python_exe, "pr", "--repo", str(integ)))
    assert opened["status"] == "waiting_for_merge"
    (work / "after-pr.txt").write_text("再追加\n")
    commit(work)
    assert error_of(mdf(python_exe, "release-integrate", "--repo", str(work)))["error"] == "release_head_changed"


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
