"""github-flow 的 PR mode：trunk 为目标、无 develop 回合、tag 固定 release_head，以及独立 pm 分支。"""
from __future__ import annotations
import json
from mdf_test_support import *  # noqa: F403
from support_delivery import write_change, write_changelog_release
from support_github_flow import commit, error_of, github_flow_repo, has_ref
from support_planning import add_prp
from support_pull import Platform, squash_pending


def pr_repo(tmp_path, monkeypatch, *, trunk="master"):
    repo, remote = github_flow_repo(tmp_path, trunk=trunk, origin=True, pr=True)
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


@pytest.mark.parametrize("reverted", [False, True])
def test_trunk_pr_moves_mixed_history_to_adhoc(python_exe, tmp_path, monkeypatch, reverted):
    repo, _, platform = pr_repo(tmp_path, monkeypatch)
    before = git(repo, "rev-parse", "master").stdout.strip()
    add_prp(repo, "prp-0002")
    git(repo, "add", "docs/proposals")
    payload(pm_commit(python_exe, repo))
    (repo / "local.txt").write_text("trunk 本地增量\n")
    commit(repo)
    if reverted:
        git(repo, "revert", "--no-edit", "HEAD")
    kept = git(repo, "rev-parse", "master").stdout.strip()
    rescue = ("trunk-pr", "--repo", str(repo), "--slug", "trunk-work")
    result = payload(mdf(python_exe, *rescue))["result"]
    assert result["kind"] == "adhoc"
    assert result["source"] == "adhoc/trunk-work" and result["next_intent"] == "trunk-pr"
    assert git(repo, "rev-parse", "master").stdout.strip() == before
    assert git(repo, "rev-parse", "adhoc/trunk-work").stdout.strip() == kept
    work = Path(result["worktree"])
    assert payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]["verification"] == "smoke"
    write_change(work, result["source"], "trunk-work")
    commit(work)
    squash_pending(work)
    request = ("pr", "--repo", str(work))
    first = payload(mdf(python_exe, *request))
    assert first["status"] == "waiting_for_merge"
    assert payload(mdf(python_exe, *rescue))["result"]["status"] == "no_pending_commits"
    assert payload(mdf(python_exe, *request))["pull_request"]["id"] == first["pull_request"]["id"]
    assert len(platform.pulls) == 1


@pytest.mark.parametrize("followup", ["rename", "test-config"])
def test_trunk_pr_rechecks_documentation_verification_after_source_changes(python_exe, tmp_path, followup):
    repo, remote = github_flow_repo(tmp_path, origin=True, pr=True)
    (repo / "docs/system/notes.md").write_text("# 说明\n")
    commit(repo)

    other = tmp_path / "other"
    git(tmp_path, "clone", str(remote), str(other))
    (other / "remote.py").write_text("enabled = True\n")
    commit(other)
    git(other, "push")

    result = payload(mdf(python_exe, "trunk-pr", "--repo", str(repo)))["result"]
    assert result["kind"] == "adhoc"
    work = Path(result["worktree"])
    request = ("adhoc-status", "--repo", str(work))
    assert payload(mdf(python_exe, *request))["result"]["verification"] == "quick"
    target = result["base"]
    git(work, "merge", "--no-ff", "--no-edit", target)
    assert payload(mdf(python_exe, *request))["result"]["verification"] == "quick"

    if followup == "rename":
        git(work, "mv", "docs/system/notes.md", "notes.py")
    else:
        (work / "docs/system/testing/named.md").write_text("---\ncommand: pytest\n---\n")
    commit(work)
    assert payload(mdf(python_exe, *request))["result"]["verification"] == "smoke"


@pytest.mark.parametrize("via_sync", [False, True])
def test_trunk_pr_moves_project_records_to_pm_and_reuses_pr(python_exe, tmp_path, monkeypatch, via_sync):
    from mdf_core.workspace.gitutil import worktree_map
    from support_sync import sync

    trunk = "team/main" if via_sync else "main"
    repo, remote, platform = pr_repo(tmp_path, monkeypatch, trunk=trunk)
    before = git(repo, "rev-parse", trunk).stdout.strip()
    trees = worktree_map(repo)
    add_prp(repo, "prp-0002", status="draft")
    git(repo, "add", "docs/proposals")
    proposal_commit = payload(pm_commit(python_exe, repo))
    review_args = ("--repo", str(repo), "--proposal", "prp-0002")
    checked = payload(mdf(python_exe, "prp-review", "check", *review_args))
    payload(mdf(python_exe, "prp-review", "ready", *review_args, "--confirmed-sha256", checked["sha256"]))
    git(repo, "add", "docs/proposals")
    review_commit = payload(pm_commit(python_exe, repo))
    (repo / "docs/JOTS.md").write_text("# Jots\n")
    git(repo, "add", "docs/JOTS.md")
    jot_commit = payload(pm_commit(python_exe, repo))
    head = git(repo, "rev-parse", trunk).stdout.strip()
    assert proposal_commit["source"] == review_commit["source"] == jot_commit["source"] == trunk
    assert jot_commit["head"] == head
    assert git(repo, "rev-parse", "HEAD^").stdout.strip() == review_commit["head"]
    assert git(repo, "rev-parse", "HEAD^^").stdout.strip() == proposal_commit["head"]
    assert not git(repo, "branch", "--list", "pm/*").stdout.strip()
    rescue = ("trunk-pr", "--repo", str(repo))
    if via_sync:
        other = tmp_path / "other"
        git(tmp_path, "clone", "--branch", trunk, str(remote), str(other))
        (other / "remote.txt").write_text("远端增量\n")
        commit(other)
        git(other, "push")
        before = git(other, "rev-parse", "HEAD").stdout.strip()
        result = payload(sync(python_exe, repo))["pull_requests"][trunk]
        assert result["source"].startswith("pm/team-main-")
    else:
        rescue += ("--slug", "project-records")
        result = payload(mdf(python_exe, *rescue))["result"]
        assert result["source"].startswith("pm/project-records-")
    source = result["source"]
    assert result["kind"] == "pm" and source.startswith("pm/")
    assert Path(result["worktree"]).resolve() == repo.resolve()
    assert worktree_map(repo) == trees
    assert git(repo, "rev-parse", source).stdout.strip() == head
    assert git(repo, "rev-parse", trunk).stdout.strip() == before
    assert not has_ref(remote, f"refs/heads/{source}")

    request = ("pr", "--repo", str(repo), "--source", source)
    rework_args = ("--repo", str(repo), "--source", source)
    assert error_of(mdf(python_exe, *request))["error"] == "squash_required"
    rework = payload(mdf(python_exe, "pm", "rework", *rework_args))
    work = Path(rework["worktree"])
    assert work != repo and git(repo, "branch", "--show-current").stdout.strip() == trunk
    assert git(repo, "rev-parse", source).stdout.strip() == head
    assert error_of(mdf(python_exe, *request))["error"] == "pm_rework_pending"
    if via_sync:
        squash_pending(work)
        payload(mdf(python_exe, "merge-no-ff", "--repo", str(work), "--commit", f"origin/{trunk}"))
    else:
        from mdf_core.workspace.squash import check
        from squash_execute import execute

        plan = check(work)
        plan.update(start_commit=plan["floor"], segments=[
            {"tip": review_commit["head"], "message": "docs(pm): 添加并评审提案"},
            {"tip": jot_commit["head"], "message": "docs(pm): 添加随手记录"},
        ])
        assert len(execute(work, plan, False, [])["commits"]) == 2
    payload(mdf(python_exe, "pm", "finish-rework", *rework_args))
    assert not work.exists() and not has_ref(repo, f"refs/heads/{rework['branch']}")
    assert git(repo, "branch", "--show-current").stdout.strip() == trunk and worktree_map(repo) == trees
    assert not has_ref(remote, f"refs/heads/{rework['branch']}")
    first = payload(mdf(python_exe, *request))
    assert first["status"] == "waiting_for_merge"
    assert payload(mdf(python_exe, *rescue))["result"]["status"] == "no_pending_commits"
    assert payload(mdf(python_exe, *request))["pull_request"]["id"] == first["pull_request"]["id"]
    assert len(platform.pulls) == 1
    merged = platform.merge(1, tmp_path)
    assert payload(mdf(python_exe, *request))["completed"]
    finished = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", source))
    assert finished["completed"]
    assert git(repo, "rev-parse", trunk).stdout.strip() == merged
    assert not has_ref(repo, f"refs/heads/{source}") and not has_ref(remote, f"refs/heads/{source}")
    assert payload(mdf(python_exe, *rescue))["result"]["status"] == "no_pending_commits"


def test_trunk_pr_resumes_pm_after_interruption_following_reset(python_exe, tmp_path, monkeypatch):
    from mdf_core.foundation.errors import MDFError
    from mdf_core.workspace import dev_pr

    repo, _ = github_flow_repo(tmp_path, origin=True, pr=True)
    add_prp(repo, "prp-0002")
    commit(repo, "docs(pm): 新增项目记录")
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    original_git = dev_pr.git

    def interrupt_git(where, *args, **kwargs):
        result = original_git(where, *args, **kwargs)
        if args[:2] == ("reset", "--keep"):
            raise MDFError("模拟 reset 后中断", code="test_interrupted")
        return result

    rescue = ("trunk-pr", "--repo", str(repo), "--slug", "records")
    with monkeypatch.context() as patch:
        patch.setattr(dev_pr, "git", interrupt_git)
        assert error_of(mdf(python_exe, *rescue))["error"] == "test_interrupted"
    source = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/pm").stdout.strip()
    assert source.startswith("pm/records-")
    result = payload(mdf(python_exe, *rescue))["result"]
    assert result["status"] == "no_pending_commits"
    assert git(repo, "rev-parse", source).stdout.strip() == head
    assert git(repo, "rev-parse", "HEAD").stdout == git(repo, "rev-parse", "origin/master").stdout


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


def pm_commit(python_exe, repo):
    return mdf(python_exe, "pm", "commit", "--repo", str(repo),
               "--message", "docs(pm): 更新项目记录")


def trunk_pr(python_exe, repo):
    return payload(mdf(python_exe, "trunk-pr", "--repo", str(repo), "--slug", "project-records"))["result"]["source"]


def test_start_uses_checked_sha_when_pm_commit_advances_trunk(python_exe, tmp_path, monkeypatch):
    from mdf_core.workspace import gitflow

    repo, _ = github_flow_repo(tmp_path, origin=True, pr=True)
    shared = git(repo, "rev-parse", "HEAD").stdout.strip()
    original = gitflow._require_base_covers_origin

    def commit_after_check(*args, **kwargs):
        start_point = original(*args, **kwargs)
        add_prp(repo, "prp-0002")
        git(repo, "add", "docs/proposals")
        payload(pm_commit(python_exe, repo))
        return start_point

    monkeypatch.setattr(gitflow, "_require_base_covers_origin", commit_after_check)
    started = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "adhoc",
                          "--name", "check-base", "--work", "验证交付基线"))
    assert started["start_commit"] == shared
    assert git(repo, "rev-parse", "HEAD").stdout.strip() != shared
    assert not list((Path(started["worktree"]) / "docs/proposals").glob("prp-0002-*"))


def test_pm_pr_uses_trunk_worktree_and_blocks_dependent_start(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = pr_repo(tmp_path, monkeypatch)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    trees = git(repo, "worktree", "list", "--porcelain").stdout
    prepared = payload(mdf(python_exe, "pm", "prepare", "--repo", str(repo)))
    assert prepared["branch"] == "master" and Path(prepared["worktree"]).resolve() == repo.resolve()
    add_prp(repo, "prp-0002")
    git(repo, "add", "docs/proposals")
    published_later = payload(pm_commit(python_exe, repo))
    assert published_later["source"] == "master" and published_later["head"] != head
    start = ("start", "--repo", str(repo), "--kind", "feature", "--proposal", "prp-0002",
             "--objectives-file", str(write_work_objectives(tmp_path)), "--roster", "solo")
    assert error_of(mdf(python_exe, *start))["error"] == "trunk_pr_required"
    source = trunk_pr(python_exe, repo)
    assert source.startswith("pm/project-records-")
    assert git(repo, "worktree", "list", "--porcelain").stdout == trees
    assert git(repo, "rev-parse", f"{source}^").stdout.strip() == head
    assert not has_ref(repo, "refs/heads/planning")
    blocked = mdf(python_exe, *start)
    assert error_of(blocked)["error"] == "pm_pr_pending"
    assert payload(mdf(python_exe, "pm", "prepare", "--repo", str(repo)))["branch"] == "master"
    assert error_of(mdf(python_exe, "to", "--repo", str(repo), "--target", source))["error"] == "unsupported_branch"
    args = ["--repo", str(repo), "--source", source]
    request = ["pr", *args]
    assert payload(mdf(python_exe, *request))["status"] == "waiting_for_merge"
    work = Path(payload(mdf(python_exe, "pm", "rework", *args))["worktree"])
    (work / "docs/context").mkdir(exist_ok=True)
    notes = work / "docs/context/notes.md"
    notes.write_text("补充项目背景\n")
    commit(work, "docs(pm): 补充背景")
    notes.write_text("修订项目背景\n")
    commit(work, "docs(pm): 修订背景")
    squash_pending(work)
    assert git(work, "rev-parse", "HEAD^").stdout.strip() == published_later["head"]
    payload(mdf(python_exe, "pm", "finish-rework", *args))
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
    assert payload(mdf(python_exe, *start))["base"] == "master"

    add_prp(repo, "prp-0003")
    git(repo, "add", "docs/proposals")
    assert payload(pm_commit(python_exe, repo))["source"] == "master"
    assert trunk_pr(python_exe, repo) != source


def test_merged_pm_does_not_block_unrelated_proposal(python_exe, tmp_path, monkeypatch):
    repo, _, platform = pr_repo(tmp_path, monkeypatch, trunk="main")
    other = add_prp(repo, "prp-95R9", status="draft")
    commit(repo, "docs(pm): 添加待评审提案")
    git(repo, "push", "origin", "main")
    add_prp(repo, "prp-0002")
    commit(repo, "docs(pm): 添加独立提案")
    source = trunk_pr(python_exe, repo)
    request = ("--repo", str(repo), "--source", source)
    first = payload(mdf(python_exe, "pr", *request))
    platform.merge(first["pull_request"]["id"], tmp_path)
    common = repo / ".git/mdf"
    old = common / "finish" / f"{source}.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({"source": source, "completed": False}))
    (common / "dev-pr.json").write_text(json.dumps({"source": source, "reset": True}))
    assert payload(mdf(python_exe, "pm", "prepare", "--repo", str(repo)))["branch"] == "main"
    review = ("--repo", str(repo), "--proposal", "prp-95R9")
    proposal = payload(mdf(python_exe, "prp-review", "check", *review))
    payload(mdf(python_exe, "prp-review", "ready", *review, "--confirmed-sha256", proposal["sha256"]))
    git(repo, "add", str(other))
    assert payload(pm_commit(python_exe, repo))["source"] == "main"
    assert trunk_pr(python_exe, repo) != source
    for _ in range(2):
        assert payload(mdf(python_exe, "finish-gitflow", *request))["completed"]


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
    payload(pm_commit(python_exe, repo))
    source = trunk_pr(python_exe, repo)
    work = tmp_path / "invalid-source"
    git(repo, "worktree", "add", str(work), source)
    (work / "outside.py").write_text("value = 1\n")
    commit(work, "chore: 添加非项目记录路径")
    git(work, "revert", "--no-edit", "HEAD")
    git(repo, "worktree", "remove", str(work))
    from mdf_core.foundation.errors import MDFError
    from mdf_core.workspace.squash import inspect
    with pytest.raises(MDFError) as forbidden:
        inspect(repo, source)
    assert forbidden.value.code == "pm_paths_forbidden"
    result = mdf(python_exe, "pr", "--repo", str(repo), "--source", source)
    assert error_of(result)["error"] == "pm_paths_forbidden"
    assert not has_ref(remote, f"refs/heads/{source}")


def test_concurrent_pm_commit_cannot_consume_index(python_exe, tmp_path, monkeypatch):
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
        if args[0] == "commit":
            concurrent.append(subprocess.run(
                [python_exe, str(script), "pm", "commit", "--repo", str(repo),
                 "--message", "docs(pm): 并发提交"],
                capture_output=True, text=True, check=False,
            ))
        return real_git(path, *args, **kwargs)

    monkeypatch.setattr(pm, "git", interleave)
    result = payload(pm_commit(python_exe, repo))
    assert len(concurrent) == 1 and error_of(concurrent[0])["error"] == "finish_busy"
    assert result["source"] == "master"
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == result["head"]
    assert git(repo, "rev-parse", "HEAD^").stdout.strip() == trunk
    assert not git(repo, "branch", "--list", "pm/*").stdout.strip()


def test_pm_proposal_feedback_can_review_and_update_same_pr(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = pr_repo(tmp_path, monkeypatch)
    proposal = add_prp(repo, "prp-0002")
    git(repo, "add", str(proposal))
    initial = payload(pm_commit(python_exe, repo))
    source = trunk_pr(python_exe, repo)
    args = ["--repo", str(repo), "--source", source]
    first = payload(mdf(python_exe, "pr", *args))
    rework = payload(mdf(python_exe, "pm", "rework", *args))
    work = Path(rework["worktree"])
    assert payload(mdf(python_exe, "pm", "rework", *args)) == rework
    review_args = ["--repo", str(work), "--proposal", "prp-0002"]
    draft = work / payload(mdf(python_exe, "prp-review", "draft", *review_args))["path"]
    draft.write_text(draft.read_text() + "\n## 评审补充\n\n明确校验范围。\n")
    checked = payload(mdf(python_exe, "prp-review", "check", *review_args))
    payload(mdf(python_exe, "prp-review", "ready", *review_args, "--confirmed-sha256", checked["sha256"]))
    outside = work / "docs/outside.md"
    outside.write_text("无关记录\n")
    git(work, "add", "docs")
    assert error_of(pm_commit(python_exe, work))["error"] == "pm_paths_forbidden"
    assert error_of(mdf(python_exe, "pm", "finish-rework", *args))["error"] == "dirty_worktree"
    git(work, "restore", "--staged", str(outside))
    outside.unlink()
    revised = payload(pm_commit(python_exe, work))
    assert revised["source"] == source and revised["head"] != initial["head"]
    assert git(repo, "rev-parse", source).stdout.strip() == initial["head"]
    assert payload(mdf(python_exe, "pm", "finish-rework", *args))["head"] == revised["head"]
    assert not work.exists() and not has_ref(repo, f"refs/heads/{rework['branch']}")
    assert git(repo, "branch", "--show-current").stdout.strip() == "master"
    updated = payload(mdf(python_exe, "pr", *args))
    assert updated["pull_request"]["id"] == first["pull_request"]["id"]
    assert git(remote, "rev-parse", source).stdout.strip() == revised["head"]
    platform.merge(1, tmp_path)
    assert payload(mdf(python_exe, "finish-gitflow", *args))["completed"]
    assert "明确校验范围" in proposal.read_text()


def test_pm_conflict_resolution_resumes_interrupted_cleanup(python_exe, tmp_path, monkeypatch):
    from mdf_core.foundation.errors import MDFError
    from mdf_core.lifecycle.pull_finish import finish_lock
    from mdf_core.workspace import pm

    repo, remote, platform = pr_repo(tmp_path, monkeypatch)
    (repo / "docs/JOTS.md").write_text("# Jots\n\n本地记录\n")
    commit(repo, "docs(pm): 添加本地记录")
    source = trunk_pr(python_exe, repo)
    args = ("--repo", str(repo), "--source", source)
    first = payload(mdf(python_exe, "pr", *args))
    trunk_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    other = tmp_path / "other"
    git(tmp_path, "clone", str(remote), str(other))
    (other / "docs/JOTS.md").write_text("# Jots\n\n远端记录\n")
    commit(other, "docs(pm): 添加远端记录")
    git(other, "push")

    rework = payload(mdf(python_exe, "pm", "rework", *args))
    work, branch = Path(rework["worktree"]), rework["branch"]
    merge_args = ("merge-no-ff", "--repo", str(work), "--commit", "origin/master")
    with finish_lock(repo):
        assert error_of(mdf(python_exe, *merge_args))["error"] == "finish_busy"
    merge = mdf(python_exe, *merge_args)
    assert error_of(merge)["error"] == "merge_conflict"
    assert error_of(mdf(python_exe, "pm", "finish-rework", *args))["error"] == "dirty_worktree"
    assert git(repo, "branch", "--show-current").stdout.strip() == "master"
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == trunk_head
    (work / "docs/JOTS.md").write_text("# Jots\n\n本地记录\n\n远端记录\n")
    commit(work, "docs(pm): 合并项目记录")
    tip = git(work, "rev-parse", "HEAD").stdout.strip()
    exclude = repo / ".git/info/exclude"
    exclude.parent.mkdir(exist_ok=True)
    with exclude.open("a") as stream:
        stream.write("\nlocal-notes.txt\n")
    ignored = work / "local-notes.txt"
    ignored.write_text("保留本地记录\n")
    refused = error_of(mdf(python_exe, "pm", "finish-rework", *args))
    assert refused["error"] == "dirty_worktree" and refused["details"]["paths"] == ["local-notes.txt"]
    assert ignored.read_text() == "保留本地记录\n"
    assert git(repo, "rev-parse", source).stdout.strip() == rework["head"]
    ignored.rename(tmp_path / ignored.name)
    original_git = pm.git

    def interrupt_git(where, *git_args, **kwargs):
        result = original_git(where, *git_args, **kwargs)
        if git_args[:2] == ("worktree", "remove"):
            raise MDFError("模拟 worktree 删除后中断", code="test_interrupted")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(pm, "git", interrupt_git)
        assert error_of(mdf(python_exe, "pm", "finish-rework", *args))["error"] == "test_interrupted"
    assert not work.exists() and has_ref(repo, f"refs/heads/{branch}")
    assert git(repo, "rev-parse", source).stdout.strip() == tip
    assert error_of(mdf(python_exe, "pr", *args))["error"] == "pm_rework_pending"
    assert payload(mdf(python_exe, "pm", "finish-rework", *args))["head"] == tip
    assert not has_ref(repo, f"refs/heads/{branch}")
    updated = payload(mdf(python_exe, "pr", *args))
    assert updated["pull_request"]["id"] == first["pull_request"]["id"]
    assert git(remote, "rev-parse", source).stdout.strip() == tip
    platform.merge(1, tmp_path)
    assert payload(mdf(python_exe, "finish-gitflow", *args))["completed"]


def test_pm_finish_rework_requires_verified_squash(python_exe, tmp_path, monkeypatch):
    from mdf_core.foundation.errors import MDFError
    from mdf_core.lifecycle.pull_finish import finish_lock
    from mdf_core.workspace import squash
    import squash_execute

    repo, _, _ = pr_repo(tmp_path, monkeypatch)
    (repo / "docs/JOTS.md").write_text("# Jots\n\n第一条\n")
    commit(repo, "docs(pm): 添加记录")
    (repo / "docs/JOTS.md").write_text("# Jots\n\n第一条\n\n第二条\n")
    commit(repo, "docs(pm): 补充记录")
    source = trunk_pr(python_exe, repo)
    args = ("--repo", str(repo), "--source", source)
    rework = payload(mdf(python_exe, "pm", "rework", *args))
    work, base = Path(rework["worktree"]), rework["head"]
    plan = squash.check(work)
    plan.update(start_commit=plan["floor"], segments=[
        {"tip": base, "message": "docs(pm): 整理记录"},
    ])
    git(work, "reset", "--hard", plan["floor"])
    assert error_of(mdf(python_exe, "pm", "finish-rework", *args))["error"] == "pull_state_changed"
    assert git(repo, "rev-parse", source).stdout.strip() == base
    git(work, "reset", "--hard", base)
    with finish_lock(repo), pytest.raises(MDFError) as busy:
        squash_execute.execute(work, plan, False, [])
    assert busy.value.code == "finish_busy"
    def interrupt(*args, **kwargs):
        raise MDFError("模拟 squash 核验凭证写入前中断", code="test_interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(squash, "record_analysis", interrupt)
        with pytest.raises(MDFError) as interrupted:
            squash_execute.execute(work, plan, False, [])
    assert interrupted.value.code == "test_interrupted"
    assert error_of(mdf(python_exe, "pm", "finish-rework", *args))["error"] == "pull_state_changed"
    result = squash_execute.execute(work, plan, True, [])
    assert payload(mdf(python_exe, "pm", "finish-rework", *args))["head"] == result["head"]
    assert not work.exists()
    assert git(repo, "branch", "--show-current").stdout.strip() == "master"


def test_pm_can_clean_up_preserved_rework_after_original_pr_merges(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = pr_repo(tmp_path, monkeypatch)
    (repo / "docs/JOTS.md").write_text("# Jots\n\n原记录\n")
    commit(repo, "docs(pm): 添加原记录")
    source = trunk_pr(python_exe, repo)
    args = ("--repo", str(repo), "--source", source)
    payload(mdf(python_exe, "pr", *args))
    rework = payload(mdf(python_exe, "pm", "rework", *args))
    work, base = Path(rework["worktree"]), rework["head"]
    (work / "docs/JOTS.md").write_text("# Jots\n\n补充记录\n")
    commit(work, "docs(pm): 补充记录")
    (work / "docs/JOTS.md").write_text("# Jots\n\n修订补充记录\n")
    commit(work, "docs(pm): 修订补充记录")
    squash_pending(work)
    tip = git(work, "rev-parse", "HEAD").stdout.strip()
    platform.merge(1, tmp_path)
    assert error_of(mdf(python_exe, "pm", "finish-rework", *args))["error"] == "pull_state_changed"
    assert git(work, "rev-parse", "HEAD").stdout.strip() == tip
    git(repo, "branch", "preserved-pm", tip)
    git(work, "reset", "--hard", base)
    assert payload(mdf(python_exe, "pm", "finish-rework", *args))["head"] == base
    assert not work.exists()
    assert git(repo, "rev-parse", "preserved-pm").stdout.strip() == tip
    assert payload(mdf(python_exe, "finish-gitflow", *args))["completed"]
    assert not has_ref(remote, f"refs/heads/{source}")


@pytest.mark.parametrize("status", ["draft", "ready"])
def test_linked_proposal_review_only_changes_markdown(python_exe, tmp_path, status):
    repo = github_flow_repo(tmp_path, trunk="main")
    proposal = add_prp(repo, "prp-0002", status=status)
    index = repo / "docs/README.md"
    links = index.read_text() + f"\n[计划](proposals/{proposal.name})\n"
    index.write_text(links)
    commit(repo)
    args = ["--repo", str(repo), "--proposal", "prp-0002"]
    if status == "ready":
        payload(mdf(python_exe, "prp-review", "draft", *args))
    proposal.write_text(proposal.read_text() + "\n## 评审补充\n\n明确校验范围。\n")
    checked = payload(mdf(python_exe, "prp-review", "check", *args))
    result = payload(mdf(python_exe, "prp-review", "ready", *args, "--confirmed-sha256", checked["sha256"]))
    assert repo / result["path"] == proposal
    assert index.read_text() == links
    assert git(repo, "status", "--porcelain").stdout.splitlines() == [f" M {result['path']}"]


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


def test_pm_rework_accepts_consecutive_verified_squashes(python_exe, tmp_path, monkeypatch):
    from mdf_core.workspace import squash
    repo, _, _ = pr_repo(tmp_path, monkeypatch)
    for number in range(2):
        (repo / "docs/JOTS.md").write_text(f"# Jots\n\n{number}\n")
        commit(repo)
    source = trunk_pr(python_exe, repo)
    args = ["--repo", str(repo), "--source", source]
    for round_index in range(2):
        work = Path(payload(mdf(python_exe, "pm", "rework", *args))["worktree"])
        if round_index == 0:
            squash_pending(work)
        for number in range(2, 4):
            (work / "docs/JOTS.md").write_text(f"# Jots\n\n{round_index}-{number}\n")
            commit(work)
        squash_pending(work)
        head = git(work, "rev-parse", "HEAD").stdout.strip()
        squash.record_analysis(work, git(work, "branch", "--show-current").stdout.strip(), head, reason="复核现有分段")
        assert payload(mdf(python_exe, "pm", "finish-rework", *args))["head"] == head
        assert git(repo, "rev-parse", source).stdout.strip() == head


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
    # 原 release ref 在 PR 已打开后改变或消失时，tag 仍绑定已合入的集成历史。
    git(work, "checkout", "--detach", release_head)
    git(repo, "update-ref", "refs/heads/release/1.3.0", release_head + "^", release_head)
    platform.merge(1, tmp_path)
    done = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", first["source"]))
    assert done["completed"] and done["tag"] == "v1.3.0"
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == release_head
    git(remote, "merge-base", "--is-ancestor", release_head, "master")
