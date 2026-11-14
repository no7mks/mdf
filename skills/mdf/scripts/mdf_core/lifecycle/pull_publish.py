"""由已核验的 PR merge 提交发布 tag 并合回 develop。"""
from mdf_core.foundation.errors import MDFError
from mdf_core.workspace.gitutil import add_linked_worktree, ensure_clean, git_in_progress_head, sibling_worktree, worktree_map
from mdf_core.workspace.merge_policy import ancestor, git, local_head, sha


def tag_release(repo, state, version):
    from mdf_core.workspace.workflow_policy import is_github_flow
    tag = f"v{version}"
    merged = state["release_head"] if is_github_flow(repo) else state["merge_commit"]
    ref = f"refs/tags/{tag}"
    local = git(repo, "rev-parse", "--verify", ref, check=False)
    if local.returncode:
        from mdf_core.lifecycle.closeout_render import changelog_excerpt, release_tag_message
        changelog = git(repo, "show", f"{merged}:CHANGELOG.md").stdout
        message = release_tag_message(tag, changelog_excerpt(changelog, version))
        git(repo, "tag", "-a", tag, merged, "--cleanup=verbatim", "-m", message)
    if (git(repo, "cat-file", "-t", ref).stdout.strip() != "tag" or sha(repo, ref) != merged):
        raise MDFError("现有 tag 与固定发布提交不符", code="tag_conflict")
    expected = git(repo, "rev-parse", ref).stdout.strip()
    remote = git(repo, "ls-remote", "origin", ref).stdout.split()
    if remote and remote[0] != expected:
        raise MDFError("远端 tag 与本次发布不符", code="tag_conflict")
    if not remote:
        git(repo, "push", "--no-follow-tags", "origin", f"{ref}:{ref}")
    state["tag"] = tag


def publish(repo, state, version):
    from mdf_core.lifecycle.pull_finish import sync_local
    from mdf_core.workspace.workflow_policy import is_github_flow
    from mdf_core.workspace.squash import require_ready

    merged = state["merge_commit"]
    git(repo, "fetch", "origin", "--prune")
    if is_github_flow(repo):
        from mdf_core.lifecycle.support_line import recheck_before_publish
        recheck_before_publish(repo, state["source"], version, target=state["target"], head=state["head"])
        if not ancestor(repo, state["release_head"], f"refs/remotes/origin/{state['target']}"):
            raise MDFError("release_head 不在目标远端历史中，不创建 tag", code="release_head_unreachable")
        tag_release(repo, state, version)
        return True
    tag_release(repo, state, version)
    remote = "refs/remotes/origin/develop"
    from mdf_core.lifecycle.publish import find_merge
    branch = f"codex/backmerge/{version}"
    tip = local_head(repo, branch)
    remote_merge = find_merge(repo, remote, merged)
    if remote_merge or (ancestor(repo, merged, remote) and (tip is None or ancestor(repo, tip, remote))):
        sync_local(repo, "develop", integrate_develop=True)
        return True
    work = sibling_worktree(repo, branch)
    occupant = worktree_map(repo).get(branch)
    if occupant is None:
        if work.exists():
            raise MDFError("回合 worktree 路径已存在", code="collision")
        if tip is None:
            add_linked_worktree(repo, branch, work, remote)
        elif ancestor(repo, tip, remote) or find_merge(repo, tip, merged):
            git(repo, "worktree", "add", str(work), branch)
        else:
            raise MDFError("现有回合分支缺少发布合并证据", code="pull_state_changed")
    elif occupant != work:
        raise MDFError("回合 worktree 与预期路径不符", code="pull_state_changed")
    back = {"source": branch, "worktree": str(work), "base": sha(repo, remote)}
    state["backmerge"] = back
    if git_in_progress_head(work):
        return False
    ensure_clean(work)
    head = sha(work, "HEAD")
    if not ancestor(repo, head, remote) and not ancestor(repo, remote, head):
        back["push_error"] = "回合分支与远端 develop 分歧，请先集成"
        return False
    if not ancestor(repo, merged, head):
        prior = git(work, "reflog", "show", "--format=%H", f"refs/heads/{branch}").stdout.splitlines()
        if any(find_merge(repo, previous, merged) for previous in dict.fromkeys(prior) if previous != head):
            raise MDFError("当前回合丢失已有发布合并，保留现场", code="pull_state_changed")
        require_ready(work)
        result = git(work, "merge", "--no-ff", "--no-commit", merged, check=False)
        if result.returncode:
            back["conflicts"] = git(work, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
            if git_in_progress_head(work):
                return False
            raise MDFError("无法开始回合 merge，保留现场", code="backmerge_failed")
        git(work, "commit", "-m", f"chore(release): 合回 {version} 到 develop")
    back_merge = find_merge(work, "HEAD", merged)
    if back_merge is None:
        raise MDFError("缺少引入发布提交的双亲回合", code="pull_state_changed")
    back["base"] = sha(work, back_merge + "^1")
    require_ready(work)
    head = sha(work, "HEAD")
    back["head"] = head
    result = git(work, "push", "--no-follow-tags", "origin", f"{head}:refs/heads/develop", check=False)
    git(repo, "fetch", "origin", "--prune")
    if ancestor(repo, merged, remote) and ancestor(repo, head, remote):
        sync_local(repo, "develop", integrate_develop=True)
        return True
    back["push_error"] = result.stderr.strip() or "远端 develop 尚未包含回合提交"
    return False
