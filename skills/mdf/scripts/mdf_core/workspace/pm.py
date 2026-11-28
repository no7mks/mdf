"""github-flow 项目记录的提交与路径约束。"""

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.workspace.gitutil import (
    current_branch, ensure_clean, git_in_progress_head, primary_worktree, repo_path, require_git_root,
    sibling_worktree, worktree_map,
)
from mdf_core.workspace.merge_policy import ancestor, commit_paths, configured, git, local_head, paths, sha
from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch


def outside_pm_paths(changed):
    return [path for path in changed if path != "docs/JOTS.md"
            and not path.startswith(("docs/proposals/", "docs/bugs/", "docs/context/"))]


def require_pm_paths(changed):
    outside = outside_pm_paths(changed)
    if outside:
        raise MDFError("pm 只接受 Proposal、Bug、Jots 与 Context 路径",
                       code="pm_paths_forbidden", details={"paths": outside})


def require_pm_diff(repo, target, head, source=""):
    from mdf_core.workspace.reconcile_channel import is_reconcile, require_history
    if is_reconcile(source):
        require_history(repo, target, head)
        return
    from mdf_core.workspace.changelog_sync import sync_version, require_sync_diff
    if version := sync_version(source):
        require_sync_diff(repo, git(repo, "merge-base", target, head).stdout.strip(), head, version)
        return
    base = git(repo, "merge-base", target, head).stdout.strip()
    require_pm_paths(paths(repo, base, head))
    for commit in git(repo, "rev-list", f"{target}..{head}").stdout.split():
        require_pm_paths(commit_paths(repo, commit))


def require_pm_merge(repo, first_parent, head, merged, source=""):
    from mdf_core.workspace.reconcile_channel import is_reconcile, require_diff
    if is_reconcile(source):
        require_pm_diff(repo, first_parent, head, source)
        require_diff(repo, first_parent, merged)
        return
    from mdf_core.workspace.changelog_sync import sync_version, require_sync_diff
    if version := sync_version(source):
        require_pm_diff(repo, first_parent, head, source)
        require_sync_diff(repo, first_parent, merged, version)
        return
    require_pm_diff(repo, first_parent, head)
    require_pm_paths(paths(repo, first_parent, merged))


def on_base_or_pending(repo, finder, identifier, base, *, ref, check_pending):
    try:
        return finder(repo, identifier, ref)
    except MDFError as exc:
        if exc.code not in {"missing_proposal", "missing_bug"} or not check_pending:
            raise
        refs = git(repo, "for-each-ref", "--format=%(refname)", "refs/heads/pm/").stdout.splitlines()
        for ref in refs:
            if ref.startswith("refs/heads/pm/rework/"):
                continue
            try:
                finder(repo, identifier, ref)
            except MDFError as pending:
                if pending.code != exc.code:
                    raise
                continue
            source = ref.removeprefix("refs/heads/")
            raise MDFError(f"{identifier} 仍在 {source}；先将包含该记录的提交同步至 {base}",
                           code="pm_pr_pending", details={"id": identifier, "base": base, "source": source}) from exc
        raise


def command_pm(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    if not is_github_flow(repo):
        raise MDFError("pm 仅用于 github-flow", code="invalid_workflow")
    if args.action != "prepare":
        from mdf_core.lifecycle.pull_finish import finish_lock
        with finish_lock(repo):
            if args.action == "commit":
                commit_pm(repo, args)
            else:
                rework(repo, args.source, finish=args.action == "finish-rework")
        return
    trunk = trunk_branch(repo)
    work = worktree_map(repo).get(trunk)
    if work != primary_worktree(repo):
        raise MDFError(f"请在主 worktree 检出 {trunk}", code="not_on_trunk")
    mode = configured(repo)["mode"]
    if not args.for_prp_review:
        ensure_clean(work)
    emit({"ok": True, "operation": "pm-prepare", "mode": mode,
          "branch": trunk, "worktree": str(work)})


def commit_pm(repo, args):
    trunk = trunk_branch(repo)
    mode = configured(repo)["mode"]
    branch = current_branch(repo)
    source = rework_source(repo, branch) if mode == "pr" else None
    if source is None and (branch != trunk or repo != primary_worktree(repo)):
        raise MDFError(f"pm commit 须在 {trunk} 或 pm 临时 worktree 执行", code="not_on_trunk")
    if git_in_progress_head(repo):
        raise MDFError("请先完成当前 Git 操作", code="dirty_worktree")
    staged = git(repo, "diff", "--cached", "--no-renames", "--name-only", "-z").stdout.split("\0")
    changed = [path for path in staged if path]
    require_pm_paths(changed)
    if not changed:
        raise MDFError("没有暂存的项目记录改动", code="no_pending_commits")

    git(repo, "commit", "-m", args.message)
    head = sha(repo, "HEAD")
    emit({"ok": True, "operation": "pm-commit", "mode": mode, "source": source or branch,
          "target": trunk, "head": head, "worktree": str(repo)})


def rework_branch(source):
    return f"pm/rework/{source.removeprefix('pm/')}"


def rework_source(repo, branch):
    if branch.startswith("pm/rework/") and repo == sibling_worktree(repo, branch):
        source = "pm/" + branch.removeprefix("pm/rework/")
        if local_head(repo, source) and worktree_map(repo).get(branch) == repo:
            return source
    return None


def rework(repo, source, *, finish):
    trunk = trunk_branch(repo)
    if repo != primary_worktree(repo) or current_branch(repo) != trunk or configured(repo)["mode"] != "pr":
        raise MDFError("pm 返工须从检出 trunk 的主 worktree 发起", code="not_on_trunk")
    if not source.startswith("pm/") or source.startswith("pm/rework/"):
        raise MDFError("需要原 pm source 分支", code="unsupported_branch")
    branch = rework_branch(source)
    work = sibling_worktree(repo, branch)
    refs = worktree_map(repo)
    occupant = refs.get(branch)
    if source in refs or (occupant is not None and occupant != work) or (work.exists() and occupant is None):
        raise MDFError("pm 返工的分支占用与预期不符", code="pull_state_changed")
    head, tip = local_head(repo, source), local_head(repo, branch)
    if head is None:
        raise MDFError("原 pm 分支不存在", code="missing_branch")
    git(repo, "fetch", "origin", "--prune")
    remote = f"refs/remotes/origin/{trunk}"
    merged = ancestor(repo, head, remote)
    if finish:
        if tip is not None:
            finish_rework(repo, source, branch, occupant, head, tip, remote, merged)
            head = tip
        work = repo
    else:
        if merged:
            raise MDFError("pm 分支已合入 trunk，请完成 close-out", code="no_pending_commits")
        require_pm_diff(repo, remote, head)
        if occupant is None:
            if tip is not None and tip != head:
                raise MDFError("pm 临时分支与源提交不一致，请核对现场", code="pull_state_changed")
            if tip is None:
                git(repo, "branch", branch, head)
            work.parent.mkdir(parents=True, exist_ok=True)
            git(repo, "worktree", "add", str(work), branch)
        head = sha(work, "HEAD")
    emit({"ok": True, "operation": "pm-finish-rework" if finish else "pm-rework",
          "source": source, "branch": trunk if finish else branch, "head": head, "worktree": str(work)})


def finish_rework(repo, source, branch, work, head, tip, remote, merged):
    from mdf_core.workspace.squash import analysis_reason, inspect, record_analysis, verified_squash

    if work is not None:
        ensure_clean(work)
        ignored = git(work, "ls-files", "--others", "--ignored", "--exclude-standard", "-z").stdout
        if ignored:
            raise MDFError("pm 临时 worktree 有 ignored 文件，请先处理再清理",
                           code="dirty_worktree", details={"paths": ignored.rstrip("\0").split("\0")})
    reason = analysis_reason(repo, branch, tip)
    if merged and tip != head:
        raise MDFError("原提交已合入 trunk，请另存返工提交后再清理",
                       code="pull_state_changed", details={"base": head, "head": tip, "worktree": str(work)})
    if not ancestor(repo, head, tip):
        if not verified_squash(repo, branch, head, tip) or not ancestor(repo, inspect(repo, source)["floor"], tip):
            raise MDFError("pm 返工需要保留原提交或提供已核验的 squash 结果", code="pull_state_changed")
    require_pm_diff(repo, remote, tip)
    if local_head(repo, branch) != tip:
        raise MDFError("pm 返工分支已变化，保留现场", code="pull_state_changed")
    git(repo, "update-ref", f"refs/heads/{source}", tip, head)
    if reason is not None:
        record_analysis(repo, source, tip, reason=reason)
    if work is not None:
        git(repo, "worktree", "remove", str(work))
    git(repo, "update-ref", "-d", f"refs/heads/{branch}", tip)
