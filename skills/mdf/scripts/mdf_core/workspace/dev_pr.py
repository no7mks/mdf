"""保全本地 develop 或 trunk 的未共享提交，再对齐远端。"""
from pathlib import Path
from uuid import uuid4

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.foundation.paths import load_manifest
from mdf_core.foundation.textutil import slugify
from mdf_core.lifecycle.delivery_state import read_json, write_json
from mdf_core.lifecycle.publish import state_path
from mdf_core.workspace.gitutil import (
    ensure_clean, primary_worktree, repo_path, require_git_root, sibling_worktree, worktree_map,
)
from mdf_core.workspace.merge_policy import ancestor, commit_paths, configured, git, paths, sha
from mdf_core.workspace.pm import require_pm_diff
from mdf_core.workspace.workflow_policy import integration_branch, is_github_flow


def record_path(repo):
    return state_path(repo, "dev-pr").parent.parent / "dev-pr.json"


def pending(repo):
    path = record_path(repo)
    if not path.exists():
        return None
    state = read_json(path)
    finish = state_path(repo, state["source"])
    done = read_json(finish) if finish.exists() else {}
    if done.get("completed") and done.get("source") == state["source"]:
        return None
    return state


def source_kind(repo, github, base, head):
    if not github:
        return "adhoc"
    try:
        require_pm_diff(repo, base, head)
    except MDFError as exc:
        if exc.code not in {"pm_paths_forbidden", "unknown_merge"}:
            raise
        return "adhoc"
    return "pm"


def verification_for_source(repo, source, target, head):
    state = pending(repo)
    if not state or state["source"] != source:
        return "smart"
    if not is_github_flow(repo):
        return "smoke"

    from mdf_core.execution.attestations import FIXED_INPUTS
    from mdf_core.execution.modules import match
    from mdf_core.reviewing.scope import review_document
    from mdf_core.workspace.project_rules import validate_rules

    rules = {"AGENTS.md", *validate_rules(load_manifest(repo)).values()}

    def documentation_only(changed):
        return all(review_document(path) and path not in rules
                   and not any(match(path, pattern) for pattern in FIXED_INPUTS) for path in changed)

    bases = git(repo, "merge-base", "--all", target, head).stdout.split()
    if len(bases) != 1 or not documentation_only(paths(repo, bases[0], head)):
        return "smoke"
    commits = git(repo, "rev-list", f"{target}..{head}").stdout.split()
    try:
        return "quick" if all(documentation_only(commit_paths(repo, commit)) for commit in commits) else "smoke"
    except MDFError as exc:
        if exc.code != "unknown_merge":
            raise
        return "smoke"


def prepare(repo, slug=None, *, expected_head=None, expected_base=None):
    """只准备本地现场；审查、验证与平台操作由 intent 委托现有 PR 流程。"""
    repo = primary_worktree(repo)
    main = integration_branch(repo)
    github = is_github_flow(repo)
    state = pending(repo)
    if configured(repo, state["head"] if state else None)["mode"] != "pr":
        raise MDFError("dev-pr/trunk-pr 仅用于 PR mode", code="pr_mode_required")
    identity = {
        "fetch": git(repo, "remote", "get-url", "--all", "origin").stdout,
        "push": git(repo, "remote", "get-url", "--push", "--all", "origin").stdout,
    }
    if state is None:
        head, base = sha(repo, f"refs/heads/{main}"), sha(repo, f"refs/remotes/origin/{main}")
        if ((expected_head is not None and head != expected_head)
                or (expected_base is not None and base != expected_base)):
            raise MDFError(f"{main} 与已确认计划不符", code="sync_plan_changed")
        if ancestor(repo, head, base):
            return {"status": "no_pending_commits", "completed": True}
        bases = git(repo, "merge-base", "--all", head, base).stdout.split()
        if len(bases) != 1:
            raise MDFError("dev-pr 需要唯一 merge-base", code="ambiguous_base")
        slug = slug or slugify(f"{main}-{head[:12]}")
        if slugify(slug) != slug:
            raise MDFError("dev-pr slug 必须为 kebab slug", code="invalid_slug")
        occupant = worktree_map(repo).get(main)
        kind = source_kind(repo, github, base, head)
        if kind == "pm":
            if occupant != repo:
                raise MDFError(f"请在主 worktree 检出 {main}", code="not_on_trunk")
            source = f"pm/{slug}-{uuid4().hex[:12]}"
            work = occupant
        else:
            source = f"adhoc/{slug}"
            work = sibling_worktree(repo, source)
        if ((kind == "adhoc" and work.exists())
                or not git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{source}", check=False).returncode
                or git(repo, "ls-remote", "origin", f"refs/heads/{source}").stdout.strip()):
            raise MDFError("source 分支或 worktree 已存在", code="collision")
        if occupant:
            ensure_clean(occupant)
        state = {"source": source, "head": head, "base": base, "merge_base": bases[0],
                 "worktree": str(work), "identity": identity, "reset": False}
        write_json(record_path(repo), state)

    work = Path(state["worktree"])
    source = state["source"]
    kind, source_name = source.split("/", 1)
    recorded_slug = source_name.rsplit("-", 1)[0] if kind == "pm" else source_name
    if state["identity"] != identity or (slug and slug != recorded_slug):
        raise MDFError("dev-pr/trunk-pr 恢复目标已变化，保留现场", code="pull_state_changed")
    if not state["reset"]:
        current = sha(repo, f"refs/heads/{main}")
        if current not in (state["head"], state["base"]):
            raise MDFError(f"{main} 出现新提交，保留现场", code="pull_state_changed")
        worktrees = worktree_map(repo)
        occupant = worktrees.get(main)
        owner = worktrees.get(source)
        if kind == "pm" and (occupant != work or owner is not None):
            raise MDFError("pm 接管所需的 trunk worktree 与记录不符，保留现场", code="pull_state_changed")
        if occupant:
            ensure_clean(occupant)
        ref = git(repo, "rev-parse", "--verify", f"refs/heads/{source}", check=False)
        if ref.returncode:
            git(repo, "branch", source, state["head"])
        elif ref.stdout.strip() != state["head"]:
            raise MDFError(f"source 未保留原 {main} HEAD", code="pull_state_changed")
        if kind == "adhoc":
            if owner is None and not work.exists():
                work.parent.mkdir(parents=True, exist_ok=True)
                git(repo, "worktree", "add", str(work), source)
            elif owner != work:
                raise MDFError("adhoc worktree 与记录不符", code="pull_state_changed")
            ensure_clean(work)
        # reset --keep 保留意外出现的未提交修改；未 checkout 的 ref 使用 CAS。
        if current != state["base"]:
            if sha(repo, f"refs/heads/{main}") != state["head"]:
                raise MDFError(f"{main} 在准备期间变化", code="pull_state_changed")
            if occupant:
                git(occupant, "reset", "--keep", state["base"])
            else:
                git(repo, "update-ref", f"refs/heads/{main}", state["base"], state["head"])
        state["reset"] = True
        write_json(record_path(repo), state)
    return {**state, "kind": kind, "status": "trunk_pr_required" if github else "dev_pr_required", "completed": False,
            "next_intent": "trunk-pr" if github else "dev-pr"}


def command_dev_pr(args, entry="dev-pr"):
    from mdf_core.lifecycle.pull_finish import finish_lock
    repo = repo_path(args.repo)
    require_git_root(repo)
    if is_github_flow(repo) != (entry == "trunk-pr"):
        raise MDFError(f"{entry} 与当前 workflow 不符；github-flow 使用 trunk-pr，gitflow 使用 dev-pr",
                       code="github_flow_unsupported" if entry == "dev-pr" else "gitflow_required")
    with finish_lock(repo):
        git(repo, "fetch", "origin", "--prune")
        emit({"ok": True, "operation": entry, "result": prepare(repo, args.slug)})


def command_trunk_pr(args):
    command_dev_pr(args, "trunk-pr")
