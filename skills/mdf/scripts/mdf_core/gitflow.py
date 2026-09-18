"""Strict Gitflow branch creation and closeout operations."""

from __future__ import annotations

from pathlib import Path

from .errors import MDFError, emit
from .gitutil import (
    add_linked_worktree,
    branch_details,
    current_branch,
    ensure_clean,
    primary_worktree,
    repo_path,
    require_git_root,
    run,
    sibling_worktree,
    unreleased_slug,
    worktree_map,
)
from .roster import (
    freeze_roster,
    resolve_roster,
    role_branch,
    role_branches,
    start_branches,
    write_roster_config,
)
from .textutil import slugify, stable_semver


ORIGIN = "origin"


def _git(repo: Path, *args: str, check: bool = True):
    return run(["git", *args], cwd=repo, check=check)


def _fetch(repo: Path) -> None:
    result = _git(repo, "remote", "get-url", ORIGIN, check=False)
    if result.returncode:
        raise MDFError("Gitflow requires remote origin", code="missing_origin")
    _git(repo, "fetch", ORIGIN, "--prune")


def _exists(repo: Path, ref: str) -> bool:
    return not _git(repo, "rev-parse", "--verify", "--quiet", ref,
                    check=False).returncode


def _synced(repo: Path, branch: str) -> None:
    local = f"refs/heads/{branch}"
    remote = f"refs/remotes/{ORIGIN}/{branch}"
    if not _exists(repo, local) or not _exists(repo, remote):
        raise MDFError(
            f"Branch {branch} and {ORIGIN}/{branch} must both exist",
            code="missing_upstream_branch",
        )
    left = _git(repo, "rev-parse", local).stdout.strip()
    right = _git(repo, "rev-parse", remote).stdout.strip()
    if left != right:
        raise MDFError(
            f"Branch {branch} must exactly match {ORIGIN}/{branch}",
            code="upstream_diverged",
        )


def default_branch(repo: Path) -> str | None:
    ref = _git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD",
               check=False)
    if ref.returncode:
        return None
    prefix = f"refs/remotes/{ORIGIN}/"
    value = ref.stdout.strip()
    return value.removeprefix(prefix) if value.startswith(prefix) else None


def require_master_default(repo: Path) -> None:
    branch = default_branch(repo)
    if branch == "main":
        raise MDFError(
            "Repository default branch is main; rename it to master first",
            code="main_default_branch",
        )
    if branch is not None and branch != "master":
        raise MDFError(
            f"Repository default branch must be master, got {branch}",
            code="invalid_default_branch",
        )


def _target(kind: str) -> str:
    return "develop" if kind in {"feature", "bugfix", "release"} else "master"


def _discard(repo: Path, created: list[tuple[str, Path]]) -> None:
    primary = primary_worktree(repo)
    for branch, path in reversed(created):
        _git(primary, "worktree", "remove", "--force", str(path), check=False)
        _git(primary, "branch", "-D", branch, check=False)


def command_start(args) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_clean(repo)
    base = _target(args.kind)
    if not _exists(repo, f"refs/heads/{base}"):
        raise MDFError(f"Branch {base} must exist", code="missing_branch")
    objectives = None
    if args.kind == "feature":
        if args.name:
            raise MDFError(
                "feature 的 slug 由 PRP 文件名决定，不要传 --name",
                code="unexpected_name",
            )
        if not args.proposal or not args.objectives_file:
            raise MDFError(
                "feature 需要 --proposal 与 --objectives-file",
                code="missing_proposal",
            )
        from .proposals import proposal_slug_on_ref, require_startable
        suffix = proposal_slug_on_ref(repo, args.proposal, base)
        objectives = Path(args.objectives_file).read_text(encoding="utf-8")
        from .constants import MARKER_RE
        if not objectives.strip() or MARKER_RE.search(objectives):
            raise MDFError("objectives 不能为空", code="missing_objectives")
        if not _git(repo, "cat-file", "-e", f"{base}:changes/unreleased/{suffix}",
                    check=False).returncode:
            raise MDFError("交付 slug 已存在", code="collision")
    elif args.kind == "bugfix":
        if args.name:
            raise MDFError(
                "bugfix 的分支名是 Bug ID，不要传 --name，使用 --bug",
                code="unexpected_name",
            )
        if not args.bug:
            raise MDFError("bugfix 需要 --bug", code="missing_bug")
        from .bugs import bug_id_on_ref, require_startable_bug
        suffix = bug_id_on_ref(repo, args.bug, base)
        unreleased = f"changes/unreleased/{slugify(suffix)}"
        if not _git(repo, "cat-file", "-e", f"{base}:{unreleased}",
                    check=False).returncode:
            raise MDFError("交付 slug 已存在", code="collision")
    else:
        if stable_semver(args.version or "") is None:
            raise MDFError("release and hotfix require stable --version",
                           code="invalid_version")
        suffix = args.version
    branch = f"{args.kind}/{suffix}"
    roster = freeze_roster(
        args.kind, args.qa, args.dev, args.reviewers,
        qa_strategy=args.qa_strategy, dev_strategy=args.dev_strategy,
        review_strategy=args.review_strategy, models=args.models,
    )
    names = start_branches(branch, roster)
    for name in names:
        if _exists(repo, f"refs/heads/{name}"):
            raise MDFError(f"Branch already exists: {name}",
                           code="branch_exists")
    created: list[tuple[str, Path]] = []
    try:
        for name in names:
            path = sibling_worktree(repo, name)
            add_linked_worktree(repo, name, path, base)
            created.append((name, path))
        work = created[0][1]
        if args.kind == "feature":
            require_startable(work, args.proposal)
        elif args.kind == "bugfix":
            require_startable_bug(work, args.bug)
        start_commit = _git(work, "rev-parse", "HEAD").stdout.strip()
        _git(work, "config", "--local",
             f"branch.{branch}.mdf-start-commit", start_commit)
        write_roster_config(work, branch, roster)
        write_identity = objectives is not None or roster["qa"] > 0
        if write_identity:
            from .delivery_state import safe, write_json
            folder = suffix if args.kind == "feature" else unreleased_slug(
                branch_details(branch)
            )
            target = safe(work, work / "changes/unreleased" / folder)
            if target.exists():
                raise MDFError("交付 slug 已存在", code="collision")
            target.mkdir(parents=True)
            identity = {
                "branch": branch, "roster": roster, "slug": folder,
                "start_commit": start_commit,
            }
            if args.kind == "feature":
                identity["proposal"] = args.proposal
            elif args.kind == "bugfix":
                identity["bug"] = args.bug
            if objectives is not None:
                dest = target / "objectives.md"
                from .moves import rewrite_repo_root_style_links
                objectives = rewrite_repo_root_style_links(
                    work, dest, objectives
                )
                dest.write_text(objectives, encoding="utf-8")
            write_json(target / "delivery.json", identity)
            _git(work, "add", "--", str(target.relative_to(work)))
            message = (
                f"docs(delivery): 确认 {args.proposal} 交付目标"
                if args.kind == "feature"
                else "docs(delivery): 冻结 roster"
            )
            _git(work, "commit", "-m", message)
    except MDFError:
        _discard(repo, created)
        raise
    created_paths = {name: path for name, path in created}
    payload = {
        "ok": True, "operation": "start", "branch": branch, "base": base,
        "start_commit": start_commit, "worktree": str(work), "pushed": False,
        "roster": roster,
        "roles": {
            role: [
                {
                    "index": index,
                    "branch": role_branch(role, branch, index),
                    "worktree": str(created_paths[
                        role_branch(role, branch, index)
                    ]),
                }
                for index in range(1, roster[role] + 1)
            ]
            for role in ("qa", "dev")
        },
    }
    emit(payload)


def _merge(repo: Path, source: str, target: str, before_commit=None) -> None:
    if current_branch(repo) != target:
        _git(repo, "checkout", target)
    result = _git(repo, "merge", "--no-ff", "--no-commit", source, check=False)
    if result.returncode:
        _git(repo, "merge", "--abort", check=False)
        raise MDFError(
            f"Merge conflict: {source} -> {target}; merge was aborted",
            code="merge_conflict",
        )
    if before_commit is not None:
        before_commit(repo)
    message = f"chore(gitflow): 合并 {source} 到 {target}"
    _git(repo, "commit", "-m", message)


def command_finish_gitflow(args) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_clean(repo)
    source = args.source or current_branch(repo)
    details = branch_details(source)
    if not details["supported"]:
        raise MDFError("finish requires a Gitflow delivery branch",
                       code="unsupported_branch")
    kind = details["kind"]
    publish = kind in {"release", "hotfix"}
    if publish:
        _fetch(repo)
        require_master_default(repo)
    targets = (
        ["develop"]
        if kind in {"feature", "bugfix"}
        else ["master", "develop"]
    )
    if args.source and not publish:
        raise MDFError("--source 只用于发布恢复", code="unsupported_branch")
    if not publish and not _exists(repo, "refs/heads/develop"):
        raise MDFError("Branch develop must exist", code="missing_branch")
    complete_feature = None
    if kind == "feature":
        from .delivery_state import locate, require_finish
        from .proposals import records
        from .prp_split import render
        root, data = locate(repo)
        require_finish(repo, root, data)
        change = root / "CHANGE.md"
        if not change.is_file():
            raise MDFError("finish 前必须补齐 Change", code="missing_change")
        from .yamlutil import read_frontmatter
        meta, _ = read_frontmatter(change)
        if meta.get("proposals") != [data["proposal"]] or meta.get("source_branch") != source:
            raise MDFError("Change 必须对应本 feature 的唯一 PRP", code="invalid_change")
        path, proposal, body = records(repo)[data["proposal"]]
        if proposal["status"] != "ready":
            raise MDFError("交付 PRP 状态不正确", code="invalid_proposal")
        proposal_rel = path.relative_to(repo)
        def complete_feature(merge_repo: Path):
            # Only a successful merge to develop can mark the result implemented.
            target_path = merge_repo / proposal_rel
            merged, merged_body = read_frontmatter(target_path)
            target_path.write_text(render({**merged, "status": "implemented"}, merged_body))
            _git(merge_repo, "add", "--", str(proposal_rel))
        finish_roster = data["roster"]
    else:
        finish_roster = resolve_roster(repo, source, kind)
    primary = primary_worktree(repo)
    trees = worktree_map(primary)
    for name in role_branches(source, finish_roster):
        if _exists(repo, f"refs/heads/{name}") or name in trees:
            raise MDFError("角色分支尚未集成", code="roles_pending")

    def merge_into(target, incoming, hook=None):
        occupant = worktree_map(primary).get(target)
        merge_at = occupant if occupant is not None else repo
        ensure_clean(merge_at)
        _merge(merge_at, incoming, target, hook)
        return merge_at

    if kind in {"feature", "bugfix"}:
        merge_into("develop", source, complete_feature)
    else:
        from .publish import publish as publish_release
        publish_release(repo, source, details["version"])
    remaining = worktree_map(primary)
    source_wt = remaining.get(source)
    if source_wt is not None:
        _git(primary, "worktree", "remove", str(source_wt))
        remaining = worktree_map(primary)
    delete_at = remaining.get(targets[-1], repo)
    if _exists(primary, f"refs/heads/{source}"):
        _git(delete_at, "branch", "-D", source)
    if repo.resolve() != primary.resolve() and repo.exists():
        _git(primary, "worktree", "remove", str(repo))
    tag = f"v{details['version']}" if publish else None
    emit(
        {
            "ok": True,
            "operation": "finish-gitflow",
            "source": source,
            "targets": targets,
            "deleted": source,
            "tag": tag,
            "pushed": publish,
        }
    )
