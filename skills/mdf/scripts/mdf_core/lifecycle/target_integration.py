"""merge/pr 内部的 target 合回与 incremental-integration 循环。"""
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.lifecycle.delivery_state import locate, read_json, write_json
from mdf_core.lifecycle.incremental_plan import build_plan
from mdf_core.workspace.gitutil import current_branch, ensure_clean, repo_path, require_git_root, git_in_progress_head
from mdf_core.workspace.merge_policy import git, sha, ancestor, configured_delivery
from mdf_core.workspace.squash import common_dir


def state_path(repo, source):
    return common_dir(repo) / "mdf/incremental-integration" / (source + ".json")


def target_commit(repo, source, target):
    if configured_delivery(repo, source)["mode"] == "pr":
        git(repo, "fetch", "origin", f"refs/heads/{target}")
        return sha(repo, "FETCH_HEAD")
    return sha(repo, f"refs/heads/{target}")


def require_current_head(repo, source, head):
    if current_branch(repo) != source or sha(repo, "HEAD") != head:
        raise MDFError("工作分支在增量验收期间变化，重新验收当前提交", code="integration_required")
    ensure_clean(repo)


def prepare(repo, source, target, *, complete=False, reviewed_head=None, summary=None):
    from mdf_core.workspace.workflow_policy import is_github_flow
    from mdf_core.workspace.gitutil import branch_details
    from mdf_core.lifecycle.consolidation import record_path, require_consolidated
    ensure_clean(repo)
    if current_branch(repo) != source:
        raise MDFError("target 集成须在工作分支执行", code="stage_branch")
    root, data = locate(repo)
    if data["branch"] != source:
        raise MDFError("该阶段须在交付 owner 工作分支执行", code="stage_branch")
    details = branch_details(source)
    from mdf_core.lifecycle.support_line import support_hotfix
    publishing = details["kind"] in {"release", "hotfix"}
    frozen = publishing and is_github_flow(repo) and not support_hotfix(repo, source, data=data)
    if frozen:
        from mdf_core.lifecycle.release_publish import require_published_source
        require_published_source(repo, details["version"] or data.get("version"), "HEAD", source=source)
    consolidation = record_path(repo, source)
    consolidated = read_json(consolidation) if consolidation.is_file() else {}
    if not consolidated.get("head") or consolidated.get("pending"):
        raise MDFError("merge/pr 前须完成 consolidate", code="consolidation_required")
    path = state_path(repo, source)
    state = read_json(path) if path.is_file() else {"base": consolidated["head"]}
    head = sha(repo, "HEAD")
    remote = target_commit(repo, source, target)
    if state.get("accepted_head") == head and ancestor(repo, remote, head):
        require_current_head(repo, source, head)
        return {"completed": True, "head": head, "target": target, "target_head": remote}
    if state.get("accepted_head"):
        state = {"base": state["accepted_head"]}
    if not ancestor(repo, state["base"], head):
        if git(repo, "diff", "--name-only", state["base"], head).stdout.strip():
            raise MDFError("增量验收基线已被改写", code="invalid_integration_base")
        state["base"] = head
    if complete:
        if reviewed_head != head or not summary or not summary.strip():
            raise MDFError("增量验收完成须提供当前 reviewed-head 与 summary", code="integration_review_required")
        if not ancestor(repo, remote, head):
            raise MDFError("target 再次前进，继续合回并增量验收", code="integration_required")
    else:
        state.update(target=target, target_head=remote)
        write_json(path, state)
        if not ancestor(repo, remote, head):
            require_current_head(repo, source, head)
            result = git(repo, "merge", "--no-ff", "--no-commit", remote, check=False)
            if result.returncode:
                raise MDFError("target 合回产生冲突，解决并提交后继续 incremental-integration", code="merge_conflict",
                               details={"base": state["base"], "target_head": remote})
            if git_in_progress_head(repo):
                git(repo, "commit", "-m", f"chore(integration): 合入 {target} 的最新提交")
            head = sha(repo, "HEAD")
    require_current_head(repo, source, head)
    plan = build_plan(repo, root, data, explicit_base=state["base"], explicit_head=head)
    require_current_head(repo, source, head)
    changed = any(plan[key]["action"] != "skip" for key in ("review", "verify", "fact"))
    changed = changed or (not frozen and bool(git(repo, "diff", "--name-only", state["base"], head).stdout.strip()))
    if complete or not changed:
        if not frozen:
            require_consolidated(repo, source)
        require_current_head(repo, source, head)
        state.update(accepted_head=head, target=target, target_head=remote, summary=summary)
        write_json(path, state)
        return {"completed": True, "head": state["accepted_head"], "target": target, "target_head": remote, "plan": plan}
    return {"completed": False, "head": head, "target": target, "plan": plan,
            "incr_consolidate": not frozen, "next_intent": "incremental-integration"}


def require_integrated(repo, source, target):
    from mdf_core.lifecycle.catchup import require_completed_attempt
    require_completed_attempt(repo, source)
    from mdf_core.lifecycle.consolidation import pending_attempt
    if pending_attempt(repo, source):
        raise MDFError("本轮文档须重新 consolidate，再继续 merge/pr", code="consolidation_required")
    from mdf_core.workspace.gitutil import branch_details
    if branch_details(source)["kind"] == "adhoc":
        from mdf_core.lifecycle.adhoc_context import material
        _, ledger = material(repo, source)
        if not ledger:
            remote = target_commit(repo, source, target)
            if not ancestor(repo, remote, "HEAD"):
                raise MDFError("先合入 target 并完成增量验收", code="integration_required")
            return {"completed": True, "head": sha(repo, "HEAD"), "target_head": remote}
    path = state_path(repo, source)
    if path.is_file():
        state = read_json(path)
        head = sha(repo, "HEAD")
        mode = configured_delivery(repo, source)["mode"]
        target_ref = f"refs/remotes/origin/{target}" if mode == "pr" else f"refs/heads/{target}"
        target_lookup = git(repo, "rev-parse", "--verify", target_ref, check=False)
        target_head = target_lookup.stdout.strip() if target_lookup.returncode == 0 else None
        if target_head and state.get("accepted_head") == head and ancestor(repo, target_head, head):
            require_current_head(repo, source, head)
            return {"completed": True, "head": head, "target": target, "target_head": target_head}
    result = prepare(repo, source, target)
    if not result["completed"]:
        raise MDFError("先完成本轮 incremental-integration，再继续 merge/pr", code="integration_required", details=result)
    return result


def command_incremental_integration(args):
    from mdf_core.workspace.workflow_policy import target_for
    from mdf_core.lifecycle.pull_finish import finish_lock
    repo = repo_path(args.repo)
    require_git_root(repo)
    source = current_branch(repo)
    with finish_lock(repo):
        result = prepare(repo, source, target_for(repo, source), complete=args.complete,
                         reviewed_head=args.reviewed_head, summary=args.summary)
    emit({"ok": True, "operation": "incremental-integration", **result})
