"""保全本地 develop 或 trunk 的未共享提交，再对齐远端。"""
from hashlib import sha256

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.foundation.paths import load_manifest
from mdf_core.foundation.textutil import slugify
from mdf_core.workspace.gitutil import (
    ensure_clean, primary_worktree, repo_path, require_git_root, sibling_worktree, worktree_map,
)
from mdf_core.workspace.merge_policy import ancestor, commit_paths, configured, git, paths, sha
from mdf_core.workspace.pm import require_pm_diff
from mdf_core.workspace.workflow_policy import integration_branch, is_github_flow, trunk_branch


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
    if git(repo, "config", "--local", "--get", f"branch.{source}.mdf-handoff", check=False).returncode:
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
    main_ref = f"refs/heads/{main}"
    head = sha(repo, main_ref)
    base = sha(repo, f"refs/remotes/origin/{main}")
    if ((expected_head is not None and head != expected_head)
            or (expected_base is not None and base != expected_base)):
        raise MDFError(f"{main} 与已确认计划不符", code="sync_plan_changed")
    mode = configured(repo, head)["mode"]
    if ancestor(repo, head, base) and (mode == "pr" or configured(repo, trunk_branch(repo))["mode"] == "pr"):
        return {"status": "no_pending_commits", "completed": True}
    if mode != "pr":
        raise MDFError("dev-pr/trunk-pr 仅用于 PR mode", code="pr_mode_required")
    bases = git(repo, "merge-base", "--all", head, base).stdout.split()
    if len(bases) != 1:
        raise MDFError("dev-pr 需要唯一 merge-base", code="ambiguous_base")
    slug = slug or slugify(f"{main}-{head[:12]}")
    if slugify(slug) != slug:
        raise MDFError("dev-pr slug 必须为 kebab slug", code="invalid_slug")
    trees = worktree_map(repo)
    occupant = trees.get(main)
    kind = source_kind(repo, github, base, head)
    if kind == "pm":
        if occupant != repo:
            raise MDFError(f"请在主 worktree 检出 {main}", code="not_on_trunk")
        identity = git(repo, "remote", "get-url", "origin").stdout.strip()
        batch = sha256(f"{identity}\0{main}\0{head}".encode()).hexdigest()[:12]
        source, work = f"pm/{slug}-{batch}", occupant
    else:
        source = f"adhoc/{slug}"
        work = sibling_worktree(repo, source)
    if occupant:
        ensure_clean(occupant)
    source_ref = f"refs/heads/{source}"
    existing = git(repo, "rev-parse", "--verify", "--quiet", source_ref, check=False)
    owner = trees.get(source)
    if ((owner is not None and (kind == "pm" or owner != work))
            or (kind == "adhoc" and owner is None and work.exists())
            or (not existing.returncode and existing.stdout.strip() != head)
            or git(repo, "ls-remote", "--refs", "origin", source_ref).stdout.strip()):
        raise MDFError("source 分支或 worktree 与本次接管不符", code="collision")
    if existing.returncode:
        git(repo, "branch", source, head)
    if kind == "adhoc":
        if owner is None:
            work.parent.mkdir(parents=True, exist_ok=True)
            git(repo, "worktree", "add", str(work), source)
        ensure_clean(work)
        # 记录该分支的验收来源，和已有 start-commit 一样随分支配置清理。
        git(repo, "config", "--local", f"branch.{source}.mdf-handoff", main)
    if sha(repo, main_ref) != head or sha(repo, source_ref) != head:
        raise MDFError("接管期间 Git ref 已变化，保留现场", code="pull_state_changed")
    if occupant:
        git(occupant, "reset", "--keep", base)
    else:
        git(repo, "update-ref", main_ref, base, head)
    return {"source": source, "head": head, "base": base, "merge_base": bases[0], "worktree": str(work),
            "kind": kind, "status": "trunk_pr_required" if github else "dev_pr_required", "completed": False,
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
