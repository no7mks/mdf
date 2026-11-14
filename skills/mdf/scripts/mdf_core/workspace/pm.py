"""github-flow 项目记录的提交与路径约束。"""

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.workspace.gitutil import (
    current_branch, ensure_clean, git_in_progress_head, repo_path, require_git_root, worktree_map,
)
from mdf_core.workspace.merge_policy import ancestor, commit_paths, configured, git, paths, sha
from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch


def outside_pm_paths(changed):
    return [path for path in changed if path != "docs/JOTS.md"
            and not path.startswith(("docs/proposals/", "docs/bugs/", "docs/context/"))]


def require_pm_paths(changed):
    outside = outside_pm_paths(changed)
    if outside:
        raise MDFError("pm 只接受 Proposal、Bug、Jots 与 Context 路径",
                       code="pm_paths_forbidden", details={"paths": outside})


def require_pm_diff(repo, target, head):
    base = git(repo, "merge-base", target, head).stdout.strip()
    require_pm_paths(paths(repo, base, head))
    for commit in git(repo, "rev-list", f"{target}..{head}").stdout.split():
        require_pm_paths(commit_paths(repo, commit))


def require_pm_merge(repo, first_parent, head, merged):
    require_pm_diff(repo, first_parent, head)
    require_pm_paths(paths(repo, first_parent, merged))


def on_base_or_pending(repo, finder, identifier, base, *, ref):
    try:
        return finder(repo, identifier, ref)
    except MDFError as exc:
        if (exc.code not in {"missing_proposal", "missing_bug"} or not is_github_flow(repo)
                or configured(repo)["mode"] != "pr"):
            raise
        refs = git(repo, "for-each-ref", "--format=%(refname)", "refs/heads/pm/").stdout.splitlines()
        for ref in refs:
            try:
                finder(repo, identifier, ref)
            except MDFError as pending:
                if pending.code != exc.code:
                    raise
                continue
            source = ref.removeprefix("refs/heads/")
            raise MDFError(f"{identifier} 仍在 {source}；先合入 {base} 并完成 close-out",
                           code="pm_pr_pending", details={"id": identifier, "base": base, "source": source}) from exc
        raise


def require_trunk_batch_available(repo, mode):
    if mode == "pr":
        from mdf_core.workspace.dev_pr import pending
        state = pending(repo)
        if state:
            source = state["source"]
            raise MDFError(f"先续办 {source} 的 trunk-pr 和 close-out，再提交下一批项目记录",
                           code="trunk_pr_required", details={"source": source})


def command_pm(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    if args.action == "commit":
        from mdf_core.lifecycle.pull_finish import finish_lock
        with finish_lock(repo):
            commit_pm(repo, args)
        return
    if not is_github_flow(repo):
        raise MDFError("pm 仅用于 github-flow", code="invalid_workflow")
    trunk = trunk_branch(repo)
    work = worktree_map(repo).get(trunk)
    if work is None:
        raise MDFError(f"请在现有 worktree 检出 {trunk}", code="not_on_trunk")
    mode = configured(repo)["mode"]
    require_trunk_batch_available(repo, mode)
    ensure_clean(work)
    emit({"ok": True, "operation": "pm-prepare", "mode": mode,
          "branch": trunk, "worktree": str(work)})


def commit_pm(repo, args):
    if not is_github_flow(repo):
        raise MDFError("pm 仅用于 github-flow", code="invalid_workflow")
    trunk = trunk_branch(repo)
    mode = configured(repo)["mode"]
    branch = current_branch(repo)
    revising = mode == "pr" and branch.startswith("pm/")
    if branch != trunk and not revising:
        raise MDFError(f"pm commit 须在 {trunk} 或待合入的 pm 分支执行", code="not_on_trunk")
    if revising and trunk in worktree_map(repo):
        raise MDFError("请在原 trunk worktree 修订 pm 分支", code="not_on_trunk")
    if not revising:
        require_trunk_batch_available(repo, mode)
    if git_in_progress_head(repo):
        raise MDFError("请先完成当前 Git 操作", code="dirty_worktree")
    staged = git(repo, "diff", "--cached", "--no-renames", "--name-only", "-z").stdout.split("\0")
    changed = [path for path in staged if path]
    require_pm_paths(changed)
    if not changed:
        raise MDFError("没有暂存的项目记录改动", code="no_pending_commits")

    if revising:
        unstaged = git(repo, "diff", "--no-renames", "--name-only", "-z").stdout.split("\0")
        overlap = sorted(set(changed).intersection(unstaged))
        if overlap:
            raise MDFError("请先隔离同一文件中的未暂存改动，确保提交后能切回 trunk",
                           code="pm_partial_stage", details={"paths": overlap})
        git(repo, "fetch", "origin", "--prune")
        base = sha(repo, "HEAD")
        remote = sha(repo, f"refs/remotes/origin/{trunk}")
        if ancestor(repo, base, remote):
            raise MDFError("pm 分支已合入 trunk，请完成 close-out", code="no_pending_commits")
        require_pm_diff(repo, remote, base)
    git(repo, "commit", "-m", args.message)
    head = sha(repo, "HEAD")
    if revising:
        switched = git(repo, "switch", "--no-overwrite-ignore", trunk, check=False)
        if switched.returncode:
            raise MDFError("提交已保存；处理 checkout 冲突后切回 trunk 续办",
                           code="pm_return_blocked", details={"source": branch, "target": trunk,
                                                              "head": head, "error": switched.stderr.strip()})
    emit({"ok": True, "operation": "pm-commit", "mode": mode, "source": branch,
          "target": trunk, "head": head, "worktree": str(repo)})
