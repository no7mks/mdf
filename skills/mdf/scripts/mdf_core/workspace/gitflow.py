"""Strict Gitflow branch creation and closeout operations."""

from __future__ import annotations

from pathlib import Path
import re

from mdf_core.lifecycle.adhoc import prepare, validate_start
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.workspace.gitutil import (
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
from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch
from mdf_core.lifecycle.roster import (
    freeze_roster,
    models_from_args,
    resolve_roster,
    role_branch,
    role_branches,
    start_branches,
    write_roster_config,
)
from mdf_core.foundation.textutil import slugify, stable_semver
from mdf_core.lifecycle.delivery_state import (
    parse_has_dev,
    parse_needs_design,
    read_objectives as _read_objectives,
)


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


def _require_base_covers_origin(repo: Path, branch: str) -> None:
    if _git(repo, "remote", "get-url", ORIGIN, check=False).returncode:
        return
    listed = _git(repo, "ls-remote", ORIGIN, f"refs/heads/{branch}", check=False)
    if listed.returncode:
        raise MDFError(f"无法读取 {ORIGIN}/{branch}", code="remote_unavailable")
    lines = listed.stdout.strip().splitlines()
    if not lines:
        return
    remote_sha = lines[0].split()[0]
    local_sha = _git(repo, "rev-parse", f"refs/heads/{branch}").stdout.strip()
    ancestor = _git(
        repo, "merge-base", "--is-ancestor", remote_sha, local_sha, check=False,
    )
    if ancestor.returncode:
        raise MDFError(
            f"本地 {branch} 缺少 {ORIGIN}/{branch} 上的提交",
            code="remote_ahead",
        )


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


def require_trunk_default(repo: Path, trunk: str = "master") -> None:
    branch = default_branch(repo)
    if branch == "main" and trunk != "main":
        raise MDFError(
            f"Repository default branch is main; rename it to {trunk} first",
            code="main_default_branch",
        )
    if branch is not None and branch != trunk:
        raise MDFError(
            f"Repository default branch must be {trunk}, got {branch}",
            code="invalid_default_branch",
        )


def _target(repo: Path, kind: str) -> str:
    from mdf_core.workspace.workflow_policy import integration_branch, trunk_branch
    if kind in {"feature", "bugfix", "release", "adhoc"}:
        return integration_branch(repo)
    return trunk_branch(repo)


def _discard(repo: Path, created: list[tuple[str, Path]]) -> None:
    primary = primary_worktree(repo)
    for branch, path in reversed(created):
        _git(primary, "worktree", "remove", "--force", str(path), check=False)
        _git(primary, "branch", "-D", branch, check=False)


def _unreleased_collision(repo: Path, base: str, folder: str) -> None:
    if not _git(
        repo, "cat-file", "-e", f"{base}:changes/unreleased/{folder}",
        check=False,
    ).returncode:
        raise MDFError("交付 slug 已存在", code="collision")


def _require_version(version: str | None) -> str:
    if stable_semver(version or "") is None:
        raise MDFError("release and hotfix require stable --version",
                       code="invalid_version")
    return version or ""


def command_start(args) -> None:
    validate_start(args)
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_clean(repo)
    from mdf_core.lifecycle.late_decision import start_options, CHECKPOINT
    from mdf_core.workspace.workflow_policy import require_gitflow
    trunk, github = trunk_branch(repo), is_github_flow(repo)
    if github:
        if getattr(args, "from_master", False):
            require_gitflow(repo, "start --from-master")
        if args.kind == "on-demand-release":
            require_gitflow(repo, "start --kind on-demand-release")
    from_master, delivery_target, features = start_options(args)
    from mdf_core.lifecycle.odr_scope import load_scope
    scope = load_scope(repo, args.scope_file) if getattr(args, "scope_file", None) else []
    if args.kind == "on-demand-release" and not (features or scope):
        raise MDFError("ODR 范围不得为空", code="missing_features")
    base = trunk if from_master else _target(repo, args.kind)
    support = None
    if github and args.kind == "hotfix":
        from mdf_core.lifecycle.support_line import hotfix_base
        base, support = hotfix_base(repo, args)
    cutpoint = None
    if getattr(args, "from_commit", None):
        if not github or args.kind != "release":
            raise MDFError("--from-commit 仅适用于 github-flow 的 release", code="invalid_arguments")
        from mdf_core.lifecycle.cutpoint import resolve_cutpoint
        cutpoint = resolve_cutpoint(repo, args.from_commit, trunk)
    creating_support = bool(support and support.get("create_from"))
    if not creating_support and not _exists(repo, f"refs/heads/{base}"):
        raise MDFError(f"Branch {base} must exist", code="missing_branch")
    if not creating_support:
        _require_base_covers_origin(repo, base)
    objectives = None
    manual, adhoc = getattr(args, "manual", False), args.kind == "adhoc"
    if manual:
        if args.kind != "feature" or args.proposal or args.bug or args.version:
            raise MDFError("--manual 仅用于无 PRP 的 feature", code="invalid_manual")
        if not args.name or slugify(args.name) != args.name:
            raise MDFError("人工 feature 需要确认的 kebab-case --name", code="invalid_slug")
        suffix = args.name
        objectives = _read_objectives(args.objectives_file)
        _unreleased_collision(repo, base, suffix)
    elif adhoc:
        suffix, objectives = prepare(args)
        _unreleased_collision(repo, base, suffix)
    elif args.kind == "feature":
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
        from mdf_core.documents.proposals import proposal_slug_on_ref, require_startable
        suffix = proposal_slug_on_ref(repo, args.proposal, base)
        objectives = _read_objectives(args.objectives_file)
        _unreleased_collision(repo, base, suffix)
    elif args.kind == "bugfix":
        if args.name:
            raise MDFError(
                "bugfix 的分支名是 Bug ID，不要传 --name，使用 --bug",
                code="unexpected_name",
            )
        if not args.bug:
            raise MDFError("bugfix 需要 --bug", code="missing_bug")
        objectives = _read_objectives(args.objectives_file)
        from mdf_core.documents.bugs import bug_id_on_ref, require_startable_bug
        suffix = bug_id_on_ref(repo, args.bug, base)
        _unreleased_collision(repo, base, slugify(suffix))
    elif args.kind in {"release", "on-demand-release"}:
        suffix = _require_version(args.version)
        objectives = _read_objectives(args.objectives_file)
        _unreleased_collision(repo, base, suffix)
    else:
        if args.name:
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.name):
                raise MDFError("hotfix --name 必须为 kebab-case slug", code="invalid_slug")
            suffix = args.name
            if args.version is not None:
                _require_version(args.version)
        else:
            suffix = _require_version(args.version)
        objectives = _read_objectives(args.objectives_file)
        _unreleased_collision(repo, base, suffix)
    from mdf_core.workspace.merge_policy import configured
    pr_mode = configured(repo)["mode"] == "pr"
    if pr_mode:
        objectives = re.sub(r"(?m)^- \[[ x]\] close-out(?:（[^\n]*）)?[ \t]*(?:\n|$)", "", objectives)
    if args.kind == "on-demand-release":
        from mdf_core.lifecycle.odr_acceptance import ACCEPTANCE
        before = r"catch-up(?:（[^\n]*）)?[ \t]*" if pr_mode else r"close-out\s*"
        objectives = re.sub(rf"(?m)^(- \[[ x]\] {before})$",
                            "- [ ] " + ACCEPTANCE + r"\n\1", objectives, count=1)
        if ACCEPTANCE not in objectives:
            objectives += "\n- [ ] " + ACCEPTANCE + "\n"
        objectives = objectives.replace("- [x] 确认工作线与范围（start）",
                                        "- [x] 确认工作线与范围（start）\n- [ ] " + CHECKPOINT)
        if "- [ ] " + CHECKPOINT not in objectives:
            if pr_mode:
                objectives = re.sub(r"(?m)^- \[[ x]\] ", "- [ ] " + CHECKPOINT + "\n" + r"\g<0>", objectives, count=1)
            else:
                objectives += "\n- [ ] " + CHECKPOINT + "\n"
    if pr_mode:
        items = re.findall(r"(?m)^- \[[ x]\] (.+?)[ \t]*$", objectives)
        steps = [item.split("（", 1)[0] for item in items]
        if not steps or steps[-1] != "catch-up" or "pr" in steps:
            raise MDFError("PR mode 的 checklist 必须止于 catch-up，且不包含 pr", code="invalid_objectives")
    branch = f"{args.kind}/{suffix}"
    roster = freeze_roster(
        args.kind, args.qa, args.dev, args.reviewers,
        named=(args.roster or "solo") if manual else args.roster, qa_strategy=args.qa_strategy,
        dev_strategy=args.dev_strategy,
        review_strategy=args.review_strategy,
        models=models_from_args(args),
    )
    if manual and (roster["qa"], roster["dev"], roster["reviewers"]) != (0, 0, 1):
        raise MDFError("人工 feature 的 roster 固定为 0,0,1", code="invalid_manual")
    needs_design = False if manual or adhoc else parse_needs_design(objectives)
    if manual:
        from mdf_core.lifecycle.manual import require_manual_objectives
        require_manual_objectives(objectives, starting=True, pr_mode=pr_mode)
    if (roster["qa"] >= 1 or roster["dev"] >= 1) and not needs_design:
        raise MDFError(
            "roster ≥1 时 needs_design 必须为 yes",
            code="invalid_needs_design",
        )
    if args.kind in {"release", "on-demand-release"}:
        parse_has_dev(objectives)
    if args.kind in {"release", "on-demand-release", "hotfix"}:
        for kind in ("release", "on-demand-release", "hotfix"):
            if kind != args.kind and _exists(repo, f"refs/heads/{kind}/{suffix}"):
                raise MDFError("该版本已有在途发布分支", code="version_in_progress")
    names = start_branches(branch, roster)
    for name in names:
        if _exists(repo, f"refs/heads/{name}"):
            raise MDFError(f"Branch already exists: {name}",
                           code="branch_exists")
    created: list[tuple[str, Path]] = []
    if creating_support:
        from mdf_core.lifecycle.support_line import ensure_support_branch
        ensure_support_branch(repo, support, trunk)
    try:
        for name in names:
            path = sibling_worktree(repo, name)
            add_linked_worktree(repo, name, path, cutpoint or base)
            created.append((name, path))
        work = created[0][1]
        if args.kind == "feature" and not manual:
            require_startable(work, args.proposal)
        elif args.kind == "bugfix":
            require_startable_bug(work, args.bug)
        start_commit = _git(work, "rev-parse", "HEAD").stdout.strip()
        _git(work, "config", "--local",
             f"branch.{branch}.mdf-start-commit", start_commit)
        write_roster_config(work, branch, roster)
        write_identity = True
        if write_identity:
            from mdf_core.lifecycle.delivery_state import safe, write_json
            folder = suffix if args.kind == "feature" else unreleased_slug(
                branch_details(branch)
            )
            target = safe(work, work / "changes/unreleased" / folder)
            if target.exists():
                raise MDFError("交付 slug 已存在", code="collision")
            target.mkdir(parents=True)
            identity = {
                "branch": branch, "roster": roster, "slug": folder,
                "start_commit": start_commit, "needs_design": needs_design,
                **({"work": args.work.strip()} if adhoc else {}),
            }
            if args.kind == "hotfix" and args.name and args.version:
                identity["version"] = args.version
            if cutpoint:
                identity.update(frozen_cutpoint=True, cutpoint_commit=cutpoint)
            if github:
                identity["target"] = base
                if support:
                    identity.update(base_branch=base, support=support)
            elif args.kind == "feature":
                identity.update(base_branch=base, target=delivery_target if from_master else "develop")
            if args.kind == "on-demand-release":
                identity.update(features=features or [], scope=scope)
            if manual:
                identity["manual"] = True
            elif args.kind == "feature":
                identity["proposal"] = args.proposal
            elif args.kind == "bugfix":
                identity["bug"] = args.bug
            if objectives is not None:
                dest = target / "objectives.md"
                from mdf_core.documents.moves import rewrite_repo_root_style_links
                objectives = rewrite_repo_root_style_links(
                    work, dest, objectives
                )
                dest.write_text(objectives, encoding="utf-8")
            write_json(target / "delivery.json", identity)
            _git(work, "add", "--", str(target.relative_to(work)))
            if adhoc:
                message = f"docs(delivery): 建立 {suffix} 临时任务"
            elif args.kind == "feature":
                message = f"docs(delivery): 确认 {suffix if manual else args.proposal} 交付目标"
            elif args.kind in {"release", "on-demand-release"}:
                message = f"docs(delivery): 确认 {args.version} 发布目标"
            elif args.kind == "bugfix":
                message = f"docs(delivery): 确认 {args.bug} 修复目标"
            else:
                message = f"docs(delivery): 确认 {suffix} 热修复目标"
            _git(work, "commit", "-m", message)
            if args.kind == "hotfix" and args.name:
                # 分支配置会随清理删除；保留最新交付起点供无源分支时恢复。
                _git(work, "config", "--local", f"mdf.hotfix-{suffix}", start_commit)
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
    from mdf_core.workspace.hooks import post_gitflow_start
    if (hook := post_gitflow_start(repo, work)) is not None:
        payload["hook"] = hook
    emit(payload)


def _merge(repo: Path, source: str, target: str, before_commit=None) -> None:
    ensure_clean(repo)
    if current_branch(repo) != target:
        _git(repo, "checkout", target)
    from mdf_core.workspace.merge_policy import require_merge
    require_merge(repo, source, target)
    new_inclusion = _git(repo, "merge-base", "--is-ancestor", source, "HEAD", check=False).returncode != 0
    result = _git(repo, "merge", "--no-ff", "--no-commit", source, check=False)
    if result.returncode:
        if result.returncode != 1:
            raise MDFError(
                result.stderr.strip() or "Git 拒绝开始合并；保留现场",
                code="command_failed",
            )
        _git(repo, "merge", "--abort", check=False)
        raise MDFError(
            f"Merge conflict: {source} -> {target}; merge was aborted",
            code="merge_conflict",
        )
    if new_inclusion and target.startswith("on-demand-release/"):
        from mdf_core.lifecycle.odr_acceptance import invalidate
        invalidate(repo, target)
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
    if details["kind"] == "adhoc":
        from mdf_core.lifecycle.adhoc_context import require_source
        require_source(source)
    from mdf_core.workspace.merge_policy import configured
    settings = configured(repo)
    if settings["mode"] == "pr":
        from mdf_core.lifecycle.pull_finish import finish
        finish(repo, source, settings, phase=getattr(args, "phase", "close-out"))
        return
    if getattr(args, "phase", "close-out") == "pr":
        raise MDFError("pr intent 仅适用于 PR mode", code="invalid_closeout")
    if details["kind"] == "adhoc":
        from mdf_core.lifecycle.adhoc_finish import finish
        finish(repo, source, recovering=bool(args.source))
        return
    kind = details["kind"]
    from mdf_core.lifecycle.late_decision import target_for, require_feature_target
    github = is_github_flow(repo)
    target = target_for(repo, source) if kind == "feature" or github else "develop"
    if not args.source and not (kind == "feature" and target.startswith("on-demand-release/")):
        from mdf_core.inspection.validate_records import require_fixed_outcomes
        require_fixed_outcomes(repo, source)
    if kind == "on-demand-release":
        from mdf_core.lifecycle.publish import state_path
        if not state_path(repo, source).exists():
            if source != current_branch(repo):
                raise MDFError("首次 ODR 发布须在 owner 执行，--source 仅恢复已开始的发布", code="invalid_delivery")
            from mdf_core.lifecycle.late_decision import checkpoint, require_independent
            checkpoint(repo, required=True, release=True)
            require_independent(repo, source)
    publish = kind in {"release", "on-demand-release", "hotfix"}
    if kind == "feature":
        require_feature_target(repo, source, target)
    targets = [target] if kind in {"feature", "bugfix"} or github else [trunk_branch(repo), "develop"]
    if args.source and not publish:
        raise MDFError("--source 只用于发布恢复", code="unsupported_branch")
    if not publish and not _exists(repo, f"refs/heads/{target}"):
        raise MDFError(f"Branch {target} must exist", code="missing_branch")
    complete_feature = None
    if kind == "feature":
        from mdf_core.lifecycle.manual import feature_completion
        complete_feature, finish_roster = feature_completion(repo, source)
    else:
        finish_roster = resolve_roster(repo, source, kind)
    primary = primary_worktree(repo)
    trees = worktree_map(primary)
    # 先只读检查全部目标，避免部分发布后才发现别人的未提交工作或 merge。
    for target in targets:
        ensure_clean(trees.get(target) or (primary if publish else repo))
    if publish:
        _fetch(repo)
        require_trunk_default(repo, trunk_branch(repo))
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
        merge_into(target, source, complete_feature)
    else:
        from mdf_core.lifecycle.publish import publish as publish_release
        if kind == "hotfix" and details["version"] is None:
            from mdf_core.lifecycle.hotfix_version import source_version
            details["version"] = source_version(repo, source)
        publish_release(repo, source, details["version"])
    remaining = worktree_map(primary)
    source_wt = remaining.get(source)
    retained = source_wt or (repo if repo != primary else None)
    if retained is not None:
        _git(retained, "checkout", "--detach")
    if _exists(primary, f"refs/heads/{source}"):
        _git(primary, "branch", "-D", source)
    tag = f"v{details['version']}" if publish else None
    emit(
        {
            "ok": True,
            "operation": "finish-gitflow",
            "source": source,
            "targets": targets,
            "deleted": source,
            "retained_worktree": str(retained) if retained is not None else None,
            "primary_worktree": str(primary),
            "tag": tag,
            "pushed": publish,
        }
    )
