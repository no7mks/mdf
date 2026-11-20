"""Strict Gitflow branch creation and closeout operations."""

from __future__ import annotations

from pathlib import Path
import re
import sys

from mdf_core.lifecycle.adhoc import prepare, validate_start
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.workspace.gitutil import (
    add_linked_worktree,
    branch_details,
    current_branch,
    ensure_clean,
    git_is_clean,
    primary_worktree,
    repo_path,
    require_git_root,
    run,
    sibling_worktree,
    unreleased_slug,
    worktree_map,
)
from mdf_core.workspace.pm import on_base_or_pending
from mdf_core.workspace.workflow_policy import GITHUB_FLOW, is_github_flow, manifest_at, parse_workflow, trunk_branch
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
    split_objectives_steps,
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


def _require_base_covers_origin(
    repo: Path, branch: str, *, shared_trunk: bool = False, cutpoint: str | None = None,
) -> str:
    local_sha = _git(repo, "rev-parse", f"refs/heads/{branch}").stdout.strip()
    start_point = cutpoint or local_sha
    if _git(repo, "remote", "get-url", ORIGIN, check=False).returncode:
        if shared_trunk:
            raise MDFError("PR mode 需要远端 origin", code="missing_origin")
        return start_point
    listed = _git(repo, "ls-remote", ORIGIN, f"refs/heads/{branch}", check=False)
    if listed.returncode:
        raise MDFError(f"无法读取 {ORIGIN}/{branch}", code="remote_unavailable")
    lines = listed.stdout.strip().splitlines()
    if not lines:
        if shared_trunk:
            raise MDFError(f"PR mode 需要 origin/{branch}", code="missing_upstream_branch")
        return start_point
    remote_sha = lines[0].split()[0]
    ancestor = _git(
        repo, "merge-base", "--is-ancestor", remote_sha, local_sha, check=False,
    )
    if ancestor.returncode:
        raise MDFError(
            f"本地 {branch} 缺少 {ORIGIN}/{branch} 上的提交",
            code="remote_ahead",
        )
    if shared_trunk and start_point != remote_sha and (
        not cutpoint or _git(repo, "merge-base", "--is-ancestor", cutpoint, remote_sha, check=False).returncode
    ):
        raise MDFError(f"本地 {branch} 有未共享 commit；先执行 trunk-pr 并完成 close-out",
                       code="trunk_pr_required", details={"branch": branch})
    return start_point


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


def require_trunk_default(repo: Path, trunk: str) -> None:
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
    from mdf_core.workspace.merge_policy import config

    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    try:
        manifest = manifest_at(repo, head)
    except MDFError as exc:
        if exc.code != "not_initialized":
            raise
        manifest = {}
    workflow = parse_workflow(manifest, repo)
    trunk, github = workflow["trunk"], workflow["model"] == GITHUB_FLOW
    pr_mode = config(manifest)["mode"] == "pr"
    if not git_is_clean(repo):
        print("警告：原 worktree 有未提交改动或未完成的 Git 操作，启动时仅使用已提交的基线。", file=sys.stderr)
    base = trunk if github or args.kind == "hotfix" else "develop"
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
    start_point = base if creating_support else _require_base_covers_origin(
        repo, base, shared_trunk=github and pr_mode and base == trunk, cutpoint=cutpoint,
    )
    objectives = None
    manual, adhoc = getattr(args, "manual", False), args.kind == "adhoc"
    if manual:
        if args.kind != "feature" or args.proposal or args.bug or args.version:
            raise MDFError("--manual 仅用于无 PRP 的 feature", code="invalid_manual")
        if not args.name or slugify(args.name) != args.name:
            raise MDFError("人工 feature 需要确认的 kebab-case --name", code="invalid_slug")
        suffix = args.name
        objectives = _read_objectives(args.objectives_file)
        _unreleased_collision(repo, start_point, suffix)
    elif adhoc:
        suffix, objectives = prepare(args)
        _unreleased_collision(repo, start_point, suffix)
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
        suffix = on_base_or_pending(repo, proposal_slug_on_ref, args.proposal, base,
                                    ref=start_point, check_pending=github and pr_mode)
        objectives = _read_objectives(args.objectives_file)
        _unreleased_collision(repo, start_point, suffix)
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
        suffix = on_base_or_pending(repo, bug_id_on_ref, args.bug, base,
                                    ref=start_point, check_pending=github and pr_mode)
        _unreleased_collision(repo, start_point, slugify(suffix))
    elif args.kind == "release":
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
    before_steps, checklist, after_steps = split_objectives_steps(objectives)
    checklist = re.sub(r"(?m)^- \[[ x]\] close-out(?:（[^\n]*）)?[ \t]*(?:\n|$)", "", checklist)
    for required in ("catch-up", "consolidate"):
        if not re.search(rf"(?m)^- \[[ x]\] {required}(?:（|$)", checklist):
            checklist = checklist.rstrip() + f"\n- [ ] {required}\n"
    publish_before_merge = github and args.kind in {"release", "hotfix"} and not support
    if publish_before_merge:
        if not re.search(r"(?m)^- \[[ x]\] publish(?:（|$)", checklist):
            checklist = checklist.rstrip() + "\n- [ ] publish（创建并推送 final tag）\n"
    items = re.findall(r"(?m)^- \[[ x]\] (.+?)[ \t]*$", checklist)
    steps = [item.split("（", 1)[0] for item in items]
    expected_last = "publish" if publish_before_merge else "consolidate"
    if not steps or steps[-1] != expected_last or "catch-up" not in steps or "consolidate" not in steps:
        raise MDFError(f"交付清单须依次包含 catch-up、consolidate，并以 {expected_last} 结束", code="invalid_objectives")
    objectives = before_steps + checklist + after_steps
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
    if args.kind == "release":
        parse_has_dev(objectives)
    if args.kind in {"release", "hotfix"}:
        for kind in ("release", "hotfix"):
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
            add_linked_worktree(repo, name, path, start_point)
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
                identity.update(base_branch=base, target=base)
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
            elif args.kind == "release":
                message = f"docs(delivery): 确认 {args.version} 发布目标"
            elif args.kind == "bugfix":
                message = f"docs(delivery): 确认 {args.bug} 修复目标"
            else:
                message = f"docs(delivery): 确认 {suffix} 热修复目标"
            _git(work, "commit", "-m", message)
            from mdf_core.workspace.squash import common_dir
            for state_kind in ("catch-up", "consolidate", "incremental-integration"):
                (common_dir(work) / "mdf" / state_kind / (branch + ".json")).unlink(missing_ok=True)
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


def _merge(repo: Path, source: str, target: str, before_commit=None, snapshot=None) -> None:
    from mdf_core.workspace.merge_guard import capture, require_snapshot, commit_merge
    ensure_clean(repo)
    delivery = snapshot is not None
    snapshot = snapshot or capture(repo, source, target)
    require_snapshot(repo, snapshot)
    if current_branch(repo) != target:
        _git(repo, "checkout", target)
    from mdf_core.workspace.merge_policy import require_merge
    require_merge(repo, source, target, delivery=delivery)
    require_snapshot(repo, snapshot)
    incoming = snapshot["head"]
    result = _git(repo, "merge", "--no-ff", "--no-commit", incoming, check=False)
    if result.returncode:
        if result.returncode != 1:
            raise MDFError(
                result.stderr.strip() or "Git 拒绝开始合并；保留现场",
                code="command_failed",
            )
        require_snapshot(repo, snapshot)
        _git(repo, "merge", "--abort", check=False)
        details = None
        from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch
        if is_github_flow(repo):
            trunk = trunk_branch(repo)
            details = {
                "recovery": (
                    f"在 {trunk} 手工执行 git merge --no-ff {source} 解决冲突并提交，"
                    "然后重跑 finish-gitflow"
                ),
                "trunk": trunk,
                "release_head": source,
            }
        raise MDFError(
            f"Merge conflict: {source} -> {target}; merge was aborted",
            code="merge_conflict",
            details=details,
        )
    if before_commit is not None:
        before_commit(repo)
    message = f"chore(gitflow): 合并 {source} 到 {target}"
    commit_merge(repo, snapshot, message)


def merge_preserving_checkout(repo, source, target, snapshot=None):
    """实际合入后恢复调用 worktree 的原分支，保留工作分支供后续阶段使用。"""
    from mdf_core.workspace.gitutil import git_in_progress_head
    from mdf_core.workspace.merge_guard import capture
    original = current_branch(repo)
    snapshot = snapshot or capture(repo, source, target)
    try:
        _merge(repo, source, target, None, snapshot)
    finally:
        if (original and current_branch(repo) != original and not git_in_progress_head(repo)
                and not _git(repo, "status", "--porcelain").stdout.strip()):
            _git(repo, "checkout", original)


def command_finish_gitflow(args) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_clean(repo)
    source = args.source or current_branch(repo)
    details = branch_details(source)
    from mdf_core.workspace.workflow_policy import forbid_support_to_trunk
    forbid_support_to_trunk(repo, source)
    from mdf_core.workspace.merge_policy import configured_delivery, local_head
    ref = None
    recovered = None
    if args.source and details["kind"] == "hotfix" and is_github_flow(repo) and local_head(repo, source) is None:
        from mdf_core.lifecycle.publish import support_merge_record
        recovered = support_merge_record(repo, source, getattr(args, "version", None))
        if recovered:
            ref = recovered[1]["head"]
        else:
            from mdf_core.lifecycle.hotfix_version import source_version
            version = details["version"] or getattr(args, "version", None) or source_version(repo, source)
            ref = f"refs/tags/v{version}"
    settings = configured_delivery(repo, source, ref=ref)
    pm_pr = details["kind"] == "pm" and is_github_flow(repo) and settings["mode"] == "pr"
    if not details["supported"] and not pm_pr:
        raise MDFError("finish requires a Gitflow delivery branch",
                       code="unsupported_branch")
    if details["kind"] == "adhoc":
        from mdf_core.lifecycle.adhoc_context import require_source
        require_source(source)
    if getattr(args, "version", None) is not None and (
            settings["mode"] == "pr" or details["kind"] != "hotfix" or details["version"] is not None):
        raise MDFError("--version 仅用于本地 slug hotfix 的收口", code="invalid_arguments")
    if settings["mode"] == "pr":
        if getattr(args, "phase", "close-out") == "merge":
            raise MDFError("merge 适用于 local 模式；PR mode 使用 pr", code="invalid_closeout")
        from mdf_core.lifecycle.pull_finish import finish
        finish(repo, source, settings, phase=getattr(args, "phase", "close-out"), number=getattr(args, "pull", None))
        return
    from mdf_core.lifecycle.pull_finish import finish_lock
    with finish_lock(repo):
        finish_local(repo, source, details, args, recovered=recovered)


def finish_local(repo, source, details, args, *, recovered=None):
    if getattr(args, "phase", "close-out") == "pr":
        raise MDFError("pr intent 仅适用于 PR mode", code="invalid_closeout")
    if details["kind"] == "adhoc":
        from mdf_core.lifecycle.adhoc_finish import finish
        finish(repo, source, recovering=bool(args.source), merging=getattr(args, "phase", "close-out") == "merge")
        return
    kind = details["kind"]
    merging = getattr(args, "phase", "close-out") == "merge"
    from mdf_core.workspace.workflow_policy import target_for
    github = is_github_flow(repo)
    from mdf_core.workspace.merge_policy import local_head
    source_head = local_head(repo, source)
    if recovered:
        details["version"], receipt = recovered
        source_head = receipt["head"]
    if kind == "hotfix" and details["version"] is None:
        from mdf_core.lifecycle.hotfix_version import source_version
        requested = getattr(args, "version", None)
        if requested is not None and source_head is None:
            from mdf_core.foundation.textutil import stable_semver
            from mdf_core.lifecycle.hotfix_version import delivery_record
            if not stable_semver(requested):
                raise MDFError("--version 需要稳定 SemVer", code="invalid_arguments")
            record = delivery_record(repo, source, ref=f"refs/tags/v{requested}")
            if record is None or record[1].get("version") != requested:
                raise MDFError("指定版本与 hotfix 的 tag 或交付材料不匹配", code="invalid_delivery")
            details["version"] = requested
        else:
            details["version"] = source_version(repo, source)
            if requested is not None and requested != details["version"]:
                raise MDFError("指定版本与源分支不匹配", code="invalid_delivery")
    target_head = source_head
    if github and kind == "hotfix" and target_head is None:
        from mdf_core.workspace.merge_policy import sha
        target_head = sha(repo, f"refs/tags/v{details['version']}")
    target = target_for(repo, source, ref=target_head) if kind == "feature" or github else "develop"
    trees = worktree_map(repo)
    owner = trees.get(source)
    if owner is not None:
        from mdf_core.inspection.validate_records import require_fixed_outcomes
        ensure_clean(owner)
        require_fixed_outcomes(owner, source)
    from mdf_core.workspace.squash import common_dir
    from mdf_core.lifecycle.delivery_state import read_json, write_json
    from mdf_core.lifecycle.publish import merge_record_path
    merge_record = merge_record_path(repo, source, details.get("version"))
    saved_merge = read_json(merge_record) if merge_record.is_file() else {}
    source_head = source_head or saved_merge.get("head")
    publish = kind in {"release", "hotfix"}
    targets = [target] if kind in {"feature", "bugfix"} or github else [trunk_branch(repo), "develop"]
    if args.source and not publish:
        raise MDFError("--source 只用于发布恢复", code="unsupported_branch")
    if not publish and not _exists(repo, f"refs/heads/{target}"):
        raise MDFError(f"Branch {target} must exist", code="missing_branch")
    finish_roster = resolve_roster(repo, source, kind)
    primary = primary_worktree(repo)
    # 先只读检查全部目标，避免部分发布后才发现别人的未提交工作或 merge。
    for target in targets:
        ensure_clean(trees.get(target) or (primary if publish else repo))
    if publish:
        _fetch(repo)
        require_trunk_default(repo, trunk_branch(repo))
        from mdf_core.lifecycle.support_line import forbid_bug_edits
        forbid_bug_edits(repo, source)
    for name in role_branches(source, finish_roster):
        if _exists(repo, f"refs/heads/{name}") or name in trees:
            raise MDFError("角色分支尚未集成", code="roles_pending")
    if kind == "feature":
        from mdf_core.lifecycle.manual import feature_completion
        feature_completion(repo, source)

    def merge_into(target, incoming, snapshot=None):
        occupant = worktree_map(primary).get(target)
        fallback = primary
        merge_at = occupant if occupant is not None else fallback
        ensure_clean(merge_at)
        merge_preserving_checkout(merge_at, incoming, target, snapshot)
        return merge_at

    merged_in = None
    actual_target = target if kind in {"feature", "bugfix"} or github else trunk_branch(repo)
    support = github and kind == "hotfix" and actual_target.startswith("support/")
    from mdf_core.lifecycle.publish import find_merge
    merged = find_merge(repo, f"refs/heads/{actual_target}", source_head) if source_head else None
    if merging:
        if publish and merged is None:
            remote_ref = f"refs/remotes/origin/{actual_target}"
            remote_tip = _git(repo, "rev-parse", "--verify", remote_ref, check=False)
            local_tip = _git(repo, "rev-parse", actual_target).stdout.strip()
            owned_pending = (saved_merge.get("pending") and saved_merge.get("merge_commit") == local_tip
                             and saved_merge.get("target_parent") == remote_tip.stdout.strip())
            if not remote_tip.returncode and remote_tip.stdout.strip() != local_tip and not owned_pending:
                raise MDFError("本地发布目标与远端不同，先同步目标分支", code="publish_state_changed")
        from mdf_core.lifecycle.target_integration import require_integrated
        if merged is None:
            accepted = require_integrated(repo, source, actual_target)
            source_head = accepted["head"]
        if support and not saved_merge.get("closed"):
            tag_ref = f"refs/tags/v{details['version']}"
            if (_exists(repo, tag_ref) or _git(repo, "ls-remote", "origin", tag_ref).stdout.strip()):
                raise MDFError("support hotfix 的发布 tag 已存在，不能合入相同版本", code="tag_conflict")
            from mdf_core.lifecycle.support_line import recheck_before_publish
            recheck_before_publish(repo, source, details["version"], target=actual_target, head=source_head)
        if merged is None:
            snapshot = {"source": source, "head": source_head, "target": actual_target,
                        "target_head": accepted["target_head"]}
            merged_in = merge_into(actual_target, source, snapshot)
            merged = find_merge(repo, f"refs/heads/{actual_target}", source_head)
            if merged is None:
                raise MDFError("target 已改变，无法核对本次 merge；保留现场", code="integration_required")
        from mdf_core.workspace.merge_policy import ancestor
        parents = _git(repo, "show", "-s", "--format=%P", merged).stdout.split()
        if (len(parents) != 2 or parents[1] != source_head
                or not ancestor(repo, parents[0], source_head)):
            write_json(merge_record, {"source": source, "head": source_head, "target": actual_target,
                                     "merge_commit": merged, "target_parent": parents[0] if parents else None, "pending": True})
            raise MDFError("target 在实际合入前前进，继续 incremental-integration 后重试 merge", code="integration_required")
        if _git(repo, "diff", "--quiet", source_head, merged, check=False).returncode:
            raise MDFError("实际 merge 含已验收 source 之外的内容；保留现场", code="integration_required")
        if support:
            from mdf_core.lifecycle.target_integration import state_path
            path = state_path(repo, source)
            state = read_json(path) if path.is_file() else {}
            if state.get("accepted_head") != source_head or state.get("target") != actual_target:
                raise MDFError("已有 support merge 缺少本轮增量验收记录；保留现场", code="integration_required")
        record = {"source": source, "head": source_head, "target": actual_target, "merge_commit": merged}
        if support:
            same_merge = all(saved_merge.get(key) == value for key, value in record.items())
            record["closed"] = same_merge and saved_merge.get("closed") is True
            if record["closed"] and saved_merge.get("published") is True:
                record["published"] = True
        write_json(merge_record, record)
        if publish:
            _git(repo, "push", "--atomic", "--no-follow-tags", "origin",
                 f"{merged}:refs/heads/{actual_target}", f"{source_head}:refs/heads/{source}")
            from mdf_core.lifecycle.publish import require_remote_merge
            require_remote_merge(repo, actual_target, merged)
        emit({"ok": True, "operation": "merge", "completed": True, "source": source, "merge_commit": merged,
              "next_intent": "publish" if publish and not github else "close-out"})
        return
    if merged is None:
        raise MDFError("先完成 merge，再执行 close-out", code="merge_required")
    if saved_merge.get("pending"):
        raise MDFError("本次 merge 尚待增量验收", code="integration_required")
    if publish:
        from mdf_core.lifecycle.publish import require_remote_merge, require_support_merge
        from mdf_core.workspace.merge_policy import ancestor
        if support:
            if any(saved_merge.get(key) != value for key, value in {
                "source": source, "target": actual_target, "head": source_head, "merge_commit": merged,
            }.items()):
                raise MDFError("先执行 merge 记录已验收的 support 合入", code="merge_required")
            require_support_merge(repo, saved_merge)
        else:
            require_remote_merge(repo, actual_target, merged)
        if github and not support:
            from mdf_core.lifecycle.release_publish import require_published_source
            require_published_source(repo, details["version"], source_head, source=source)
        elif not github:
            from mdf_core.lifecycle.release_publish import published_head
            if published_head(repo, details["version"]) != merged:
                raise MDFError("final tag 与已合入结果不符", code="tag_conflict")
        if not github and not ancestor(repo, merged, "refs/heads/develop"):
            merge_into("develop", merged)
        from mdf_core.lifecycle.pull_finish import cleanup_remote
        cleanup_remote(repo, source, source_head)
    source_wt = worktree_map(primary).get(source)
    from mdf_core.lifecycle.pull_finish import cleanup, retained_owner
    cleanup(repo, {"source": source, "head": source_head})
    if support:
        write_json(merge_record, {**saved_merge, "closed": True})
    retained = source_wt
    if owner is not None and owner == merged_in and owner != primary and source_wt is None:
        ensure_clean(owner)
        _git(owner, "checkout", "--detach", source_head)
        retained = owner
    if retained is None:
        retained = retained_owner(repo, source, source_head)
    tag = f"v{details['version']}" if publish and not support else None
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
            **({"next_intent": "publish", "version": details["version"]} if support else {}),
        }
    )
