"""github-flow 项目记录的提交与路径约束。"""

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.workspace.gitutil import (
    current_branch, ensure_clean, git_in_progress_head, primary_worktree, repo_path, require_git_root,
    sibling_worktree, worktree_map,
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
    require_trunk_batch_available(repo, mode)
    ensure_clean(work)
    emit({"ok": True, "operation": "pm-prepare", "mode": mode,
          "branch": trunk, "worktree": str(work)})


def commit_pm(repo, args):
    trunk = trunk_branch(repo)
    mode = configured(repo)["mode"]
    branch = current_branch(repo)
    source = rework_source(repo, branch) if mode == "pr" else None
    if source is None:
        if branch != trunk or repo != primary_worktree(repo):
            raise MDFError(f"pm commit 须在 {trunk} 或 pm 临时 worktree 执行", code="not_on_trunk")
        require_trunk_batch_available(repo, mode)
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


def rework_record(repo):
    from mdf_core.workspace.dev_pr import record_path
    return record_path(repo).with_name("pm-rework.json")


def rework_state(repo):
    from mdf_core.lifecycle.delivery_state import read_json
    path = rework_record(repo)
    return read_json(path) if path.exists() else None


def rework_source(repo, branch):
    if branch.startswith("pm/rework/"):
        state = rework_state(repo)
        if state and state["branch"] == branch and "result" not in state and repo == sibling_worktree(repo, branch):
            return state["source"]
    return None


def squash_rework(repo, branch, old_tip, *, new_tip=None):
    """记录当前返工中经 squash 脚本校验的历史替换。"""
    from mdf_core.lifecycle.delivery_state import write_json

    if rework_source(repo, branch) is None:
        raise MDFError("需要已登记的 pm 临时 worktree", code="invalid_worktree")
    state = rework_state(repo)
    if new_tip is None:
        require_rework_history(repo, state, old_tip)
        state["squash_in_progress"] = old_tip
    else:
        if state.get("squash_in_progress") != old_tip:
            raise MDFError("没有与本次计划匹配的 pm squash 操作", code="pull_state_changed")
        state.pop("squash_in_progress")
        state["squash_head"] = new_tip
    write_json(rework_record(repo), state)


def require_rework_history(repo, state, tip):
    pending_tip = state.get("squash_in_progress")
    if pending_tip is not None and tip != pending_tip:
        raise MDFError("pm squash 尚未完成验证，保留临时现场", code="pull_state_changed")
    if not ancestor(repo, state.get("squash_head", state["base"]), tip):
        raise MDFError("pm 返工未保留原批次或已验证的 squash 结果", code="pull_state_changed")


def rework(repo, source, *, finish):
    from mdf_core.lifecycle.delivery_state import write_json
    from mdf_core.workspace.dev_pr import pending

    trunk = trunk_branch(repo)
    if repo != primary_worktree(repo) or current_branch(repo) != trunk or configured(repo)["mode"] != "pr":
        raise MDFError("pm 返工须从检出 trunk 的主 worktree 发起", code="not_on_trunk")
    batch = pending(repo)
    if not batch or not batch["reset"] or batch["source"] != source or not source.startswith("pm/"):
        raise MDFError("找不到待续办的 pm 接管批次", code="no_pending_commits")

    branch = f"pm/rework/{source.removeprefix('pm/')}"
    work = sibling_worktree(repo, branch)
    refs = worktree_map(repo)
    if source in refs or (branch in refs and refs[branch] != work):
        raise MDFError("pm 返工的分支占用与预期不符", code="pull_state_changed")
    head = sha(repo, f"refs/heads/{source}")
    path = rework_record(repo)
    state = rework_state(repo)
    if state and (state["source"] != source or state["branch"] != branch):
        raise MDFError("pm 返工记录与本次接管不符", code="pull_state_changed")
    if finish:
        head = finish_rework(repo, trunk, source, branch, work, head, state)
        work = repo
    else:
        if state is None:
            if work.exists() or branch in refs or git(repo, "show-ref", "--verify", "--quiet",
                                                       f"refs/heads/{branch}", check=False).returncode == 0:
                raise MDFError("pm 临时分支或 worktree 已存在", code="collision")
            git(repo, "fetch", "origin", "--prune")
            remote = f"refs/remotes/origin/{trunk}"
            if ancestor(repo, head, remote):
                raise MDFError("pm 分支已合入 trunk，请完成 close-out", code="no_pending_commits")
            require_pm_diff(repo, remote, head)
            state = {"source": source, "branch": branch, "base": head}
            write_json(path, state)
        if "result" in state or head != state["base"]:
            raise MDFError("pm 返工源已变化或进入清理，请核对后续办", code="pull_state_changed")
        if branch not in refs:
            ref = f"refs/heads/{branch}"
            existing = git(repo, "rev-parse", "--verify", ref, check=False)
            if work.exists() or (existing.returncode == 0 and existing.stdout.strip() != head):
                raise MDFError("pm 临时现场与返工记录不符", code="pull_state_changed")
            work.parent.mkdir(parents=True, exist_ok=True)
            if existing.returncode:
                git(repo, "branch", branch, head)
            git(repo, "worktree", "add", str(work), branch)
        head = sha(repo, f"refs/heads/{branch}")
    emit({"ok": True, "operation": "pm-finish-rework" if finish else "pm-rework",
          "source": source, "branch": trunk if finish else branch, "head": head, "worktree": str(work)})


def finish_rework(repo, trunk, source, branch, work, head, state):
    from mdf_core.lifecycle.delivery_state import write_json
    from mdf_core.workspace.squash import analysis_reason, inspect, record_analysis

    if state is None:
        if work.exists() or git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0:
            raise MDFError("临时现场缺少 pm 返工记录", code="pull_state_changed")
        return head
    path = rework_record(repo)
    source_ref = f"refs/heads/{source}"
    branch_ref = f"refs/heads/{branch}"
    occupant = worktree_map(repo).get(branch)
    tip = git(repo, "rev-parse", "--verify", branch_ref, check=False).stdout.strip()
    base = state["base"]
    result = state.get("result")
    if occupant is not None:
        ensure_clean(work)
        ignored = git(work, "ls-files", "--others", "--ignored", "--exclude-standard", "-z").stdout
        if ignored:
            raise MDFError("pm 临时 worktree 有 ignored 文件，请先处理再清理",
                           code="dirty_worktree", details={"paths": ignored.rstrip("\0").split("\0")})
    if result is None:
        if occupant is None or head != base:
            raise MDFError("pm 临时 worktree 或源 ref 已变化，保留现场", code="pull_state_changed")
        git(repo, "fetch", "origin", "--prune")
        remote = f"refs/remotes/origin/{trunk}"
        if ancestor(repo, base, remote):
            if tip != base:
                raise MDFError("pm 原提交已合入 trunk，请另存返工提交并恢复临时分支到原提交后清理",
                               code="pull_state_changed", details={"base": base, "head": tip, "worktree": str(work)})
        else:
            require_rework_history(repo, state, tip)
            require_pm_diff(repo, remote, tip)
            if not ancestor(repo, base, tip) and not ancestor(repo, inspect(repo, source)["floor"], tip):
                raise MDFError("pm 返工改写了受保护的历史", code="pull_state_changed")
        result = tip
        write_json(path, {**state, "result": result})
    if head not in {base, result} or (tip and tip != result) or (work.exists() and occupant is None):
        raise MDFError("pm 返工引用或 worktree 已变化，保留现场", code="pull_state_changed")
    if head != result:
        git(repo, "update-ref", source_ref, result, base)
    reason = analysis_reason(repo, branch, result)
    if reason is not None:
        record_analysis(repo, source, result, reason=reason)
    if occupant is not None:
        git(repo, "worktree", "remove", str(work))
    if tip:
        git(repo, "update-ref", "-d", branch_ref, result)
    path.unlink()
    return result
