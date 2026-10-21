"""PR 发布后的固定 tag 和可恢复 develop 回合。"""
from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.delivery_state import write_json
from mdf_core.workspace.gitutil import add_linked_worktree, ensure_clean, git_in_progress_head, sibling_worktree, worktree_map
from mdf_core.workspace.merge_policy import ancestor, git, sha


def tag_release(repo, state, version, path):
    tag, merged = f"v{version}", state["merge_commit"]
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
    write_json(path, state)


def publish(repo, state, version, forge, path):
    from mdf_core.lifecycle.pull_finish import sync_local, verified_merge
    tag_release(repo, state, version, path)
    merged = state["merge_commit"]
    git(repo, "fetch", "origin", "--prune")
    remote = "refs/remotes/origin/develop"
    if ancestor(repo, merged, remote):
        sync_local(repo, "develop")
        return True
    sync_local(repo, "develop")
    record = state.get("backmerge")
    if record is None:
        branch = f"codex/backmerge/{version}"
        work = sibling_worktree(repo, branch)
        record = {"source": branch, "worktree": str(work), "base": sha(repo, remote), "via_pr": False}
        if work.exists() or not git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode:
            raise MDFError("回合分支或 worktree 已存在", code="collision")
        state["backmerge"] = record
        write_json(path, state)
    from pathlib import Path
    work = Path(record["worktree"])
    occupant = worktree_map(repo).get(record["source"])
    if occupant is None and not work.exists():
        add_linked_worktree(repo, record["source"], work, record["base"])
    elif occupant != work:
        raise MDFError("回合 worktree 与记录不符", code="pull_state_changed")
    if git_in_progress_head(work):
        record["via_pr"] = True
        write_json(path, state)
        return False
    ensure_clean(work)
    previous_head = record.get("head")
    if previous_head and not ancestor(repo, previous_head, sha(work, "HEAD")):
        raise MDFError("回合分支历史已改写，保留现场", code="pull_state_changed")
    if not ancestor(repo, merged, "refs/heads/" + record["source"]):
        result = git(work, "merge", "--no-ff", "--no-commit", merged, check=False)
        if result.returncode:
            record["via_pr"] = True
            record["conflicts"] = git(work, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
            write_json(path, state)
            if git_in_progress_head(work):
                return False
            raise MDFError("无法开始回合 merge，保留现场", code="backmerge_failed")
        git(work, "commit", "-m", f"chore(release): 合回 {version} 到 develop")
    head = sha(work, "HEAD")
    if previous_head and previous_head != head:
        record["via_pr"] = True
    record["head"] = head
    write_json(path, state)
    if not record["via_pr"]:
        result = git(work, "push", "--no-follow-tags", "origin", f"{head}:refs/heads/develop", check=False)
        if result.returncode:
            record["via_pr"] = True
            write_json(path, state)
        git(repo, "fetch", "origin", "--prune")
        if ancestor(repo, merged, remote):
            sync_local(repo, "develop")
            return True
    pull = forge.get(record["pull"]["id"]) if record.get("pull") else forge.find(record["source"], "develop")
    if pull and (pull["source"] != record["source"] or pull["target"] != "develop"):
        raise MDFError("回合 PR 来源或目标已变化", code="pull_state_changed")
    if pull is None or pull["state"] == "open":
        if pull and not ancestor(repo, pull["head"], head):
            raise MDFError("远端回合 source 未被本地包含，先同步后续办", code="pull_state_changed")
        git(work, "push", "--no-follow-tags", "origin", f"{head}:refs/heads/{record['source']}")
        if pull is None:
            pull = forge.create(record["source"], "develop", f"chore(release): 合回 {version}",
                                f"固定发布提交：{merged}。请解决回合问题后再次执行 $mdf close-out。")
        else:
            pull = forge.get(pull["id"])
        if pull["head"] != head:
            raise MDFError("回合 PR 的 head 与已推送提交不符", code="pull_state_changed")
    record["pull"] = pull
    write_json(path, state)
    if pull["state"] != "merged":
        return False
    git(repo, "fetch", "origin", "--prune")
    verified_merge(repo, pull, record["source"], "develop", head)
    if not ancestor(repo, merged, remote):
        raise MDFError("回合 PR 未包含发布提交", code="pull_state_changed")
    sync_local(repo, "develop")
    return True
