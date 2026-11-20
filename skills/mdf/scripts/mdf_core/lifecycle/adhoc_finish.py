"""Adhoc 收口以源 ref、目标合并拓扑与交付材料为依据。"""
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.lifecycle.adhoc_context import context, require_source
from mdf_core.lifecycle.publish import find_merge
from mdf_core.workspace.gitutil import ensure_clean, primary_worktree, worktree_map
from mdf_core.workspace.merge_policy import ancestor, configured, git, local_head, sha
from mdf_core.workspace.workflow_policy import integration_branch


def status(repo, source, slug=None):
    require_source(source)
    integ = integration_branch(repo)
    branch = git(repo, "branch", "--show-current").stdout.strip()
    head = sha(repo, "HEAD")
    exists = local_head(repo, source)
    pr = configured(repo)["mode"] == "pr"
    target = f"refs/remotes/origin/{integ}" if pr else f"refs/heads/{integ}"
    if branch == integ and source != integ and exists is None and not pr:
        from mdf_core.lifecycle.adhoc_context import material
        root, _ = material(repo, source, slug)
        if (root / "CHANGE.md").is_file():
            introduced = git(repo, "log", "--first-parent", "--diff-filter=A", "--format=%H", "--",
                             str((root / "CHANGE.md").relative_to(repo))).stdout.splitlines()
            if len(introduced) == 1:
                parents = git(repo, "show", "-s", "--format=%P", introduced[0]).stdout.split()
                if len(parents) == 2:
                    head = parents[1]
    merged = find_merge(repo, target, head)
    if branch != source:
        ensure_clean(repo)
        if (branch and (branch != integ or pr)) or (exists is not None and exists != head) or not merged:
            raise MDFError("adhoc-status 需要原 source worktree 或已合入的 detached worktree", code="stage_branch")
    result = context(repo, source, slug, head=head)
    if merged and not result["has_change"]:
        merged = None
    completed = bool(merged and exists is None)
    if pr and completed:
        from mdf_core.lifecycle.pull_finish import remote_source_head
        completed = remote_source_head(repo, source) is None
    result.update(completed=completed, merge_commit=merged,
                  next_step=None if completed else ("close-out" if merged else "pr" if pr else "merge"),
                  owner_worktree=str(repo), primary_worktree=str(primary_worktree(repo)))
    if not merged and ancestor(repo, head, result["range"]["target_head"]):
        result.update(next_step=None, no_pending_commits=True)
    if result["next_step"] == "pr":
        from mdf_core.workspace.dev_pr import verification_for_source
        result["verification"] = verification_for_source(repo, source, result["range"]["target_head"], head)
    return result


def finish(repo, source, *, recovering, merging=False):
    from mdf_core.lifecycle.adhoc import completion
    from mdf_core.lifecycle.pull_finish import cleanup, retained_owner
    from mdf_core.workspace.gitflow import merge_preserving_checkout

    require_source(source)
    integ = integration_branch(repo)
    trees = worktree_map(repo)
    source_owner = trees.get(source)
    owner = source_owner or repo
    ensure_clean(owner)
    target = trees.get(integ, primary_worktree(repo))
    ensure_clean(target)
    head = local_head(repo, source)
    if head is None and recovering:
        name = git(owner, "branch", "--show-current").stdout.strip()
        if not name:
            head = sha(owner, "HEAD")
        elif name == integ:
            result = status(owner, source)
            if result["completed"]:
                head = result["head"]
    if head is None:
        raise MDFError("缺少原 source；请从保留的 worktree 或指定已核实的源提交续办", code="missing_branch")
    ref = f"refs/heads/{integ}"
    merged = find_merge(repo, ref, head)
    if not merged and (local_head(repo, source) is None or ancestor(repo, head, ref)):
        raise MDFError("没有待合入提交，也找不到原双亲 merge", code="no_pending_commits")
    if not merged and git(owner, "branch", "--show-current").stdout.strip() != source:
        raise MDFError("请在源 worktree 核对 Change 和待合入提交", code="stage_branch")
    if local_head(repo, source) is not None:
        from mdf_core.inspection.validate_records import require_fixed_outcomes
        require_fixed_outcomes(owner, source)
    completion(owner, source)
    if merging:
        if merged is None:
            from mdf_core.lifecycle.target_integration import require_integrated
            accepted = require_integrated(owner, source, integ)
            head = accepted["head"]
            snapshot = {"source": source, "head": head, "target": integ, "target_head": accepted["target_head"]}
            merge_preserving_checkout(target, source, integ, snapshot)
            merged = find_merge(repo, ref, head)
        from mdf_core.lifecycle.publish import merge_record_path
        from mdf_core.lifecycle.delivery_state import write_json
        write_json(merge_record_path(repo, source),
                   {"source": source, "head": head, "target": integ, "merge_commit": merged})
        emit({"ok": True, "operation": "merge", "completed": True, "source": source,
              "merge_commit": merged, "next_intent": "close-out"})
        return
    if merged is None:
        raise MDFError("先完成 merge，再执行 close-out", code="merge_required")
    if merged is None:
        raise MDFError("无法核对原双亲 merge", code="finish_state_changed")
    cleanup(repo, {"source": source, "head": head})
    primary = primary_worktree(repo)
    if owner == source_owner and owner != primary and sha(owner, "HEAD") == merged:
        git(owner, "checkout", "--detach", head)
    elif owner == primary and not git(owner, "branch", "--show-current").stdout.strip():
        if integ not in worktree_map(repo):
            git(owner, "checkout", integ)
    retained = source_owner or retained_owner(repo, source, head)
    emit({"ok": True, "operation": "finish-gitflow", "mode": "local", "source": source,
          "targets": [integ], "completed": True, "merge_commit": merged, "deleted": source,
          "retained_worktree": str(retained) if retained is not None else None,
          "primary_worktree": str(primary), "tag": None, "pushed": False})
