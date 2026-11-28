"""按 workflow 与 closeout.mode 准备补账工作区。"""
from pathlib import Path

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.delivery_state import write_json, read_json
from mdf_core.reconciliation.context import inspect, state_path
from mdf_core.workspace.gitutil import add_linked_worktree, ensure_clean, sibling_worktree, worktree_map
from mdf_core.workspace.merge_policy import ancestor, git, local_head, sha
from mdf_core.workspace.workflow_policy import trunk_branch


def prepare(repo, args):
    plan = inspect(repo, args)
    ensure_clean(repo)
    if plan.get("resume"):
        return plan
    if plan["record_mode"] == "ledgerless":
        work, source = repo, plan["source"]
    else:
        releases = plan["releases"]
        if not releases:
            return {**plan, "completed": True, "worktree": str(repo)}
        label = releases[0]["version"] + ("-" + releases[-1]["version"] if len(releases) > 1 else "")
        source = f"pm/reconcile-{label}"
        target = trunk_branch(repo)
        if plan["workflow"] == "gitflow" and plan["settings"]["mode"] == "local":
            from mdf_core.workspace.planning import ensure_planning
            info = ensure_planning(repo)
            work, source = Path(info["worktree"]), "planning"
            ensure_clean(work)
        else:
            work = sibling_worktree(repo, source)
            occupant = worktree_map(repo).get(source)
            if occupant and occupant != work:
                raise MDFError("reconcile 分支被其他工作区占用", code="invalid_worktree")
            if occupant is None:
                if work.exists() or local_head(repo, source):
                    raise MDFError("reconcile 工作区已存在但未登记，保留现场", code="collision")
                if plan["settings"]["mode"] == "pr":
                    git(repo, "fetch", "--no-tags", "origin", f"refs/heads/{target}:refs/remotes/origin/{target}")
                    base = f"refs/remotes/origin/{target}"
                else:
                    base = f"refs/heads/{target}"
                add_linked_worktree(repo, source, work, base)
            ensure_clean(work)
    path = state_path(work, source)
    previous = read_json(path) if path.is_file() else None
    plan.update(source=source, worktree=str(work), target=trunk_branch(repo), base_head=sha(work, "HEAD"))
    if previous and not previous.get("completed"):
        identity = ("record_mode", "release_line", "version", "releases")
        if any(previous.get(key) != plan.get(key) for key in identity):
            raise MDFError("既有 reconcile 操作身份不同，保留现场", code="reconcile_state_changed")
        if not ancestor(work, previous["base_head"], "HEAD"):
            raise MDFError("在途补账工作区丢失原基线", code="reconcile_state_changed")
        return previous
    write_json(path, plan)
    return plan
