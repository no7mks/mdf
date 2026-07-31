import argparse
from pathlib import Path
from typing import Any

from . import doctor
from .archive import archive_plan, change_move_plan, find_planning_candidates
from .constants import (
    PLANNING_ROOTS,
    PROTOCOL_VERSION,
    SCHEMA_VERSION,
    TOOL_VERSION,
)
from .digests import text_diff
from .errors import Finding, MDFError, emit, serialize_findings
from .gitutil import (
    branch_details,
    current_branch,
    ensure_clean,
    git_is_clean,
    git_root,
    repo_path,
    require_git_root,
)
from .init_repo import init_files, parse_baselines, write_files
from .moves import (
    apply_moves_and_rewrites,
    describe_moves,
    describe_rewrites,
    replacement_plan,
)
from .paths import (
    ensure_safe_managed_paths,
    load_manifest,
    manifest_path,
    relative,
)
from .semver import bump_kind, required_bump
from .textutil import new_ulid, slugify, stable_semver


def command_info(_: argparse.Namespace) -> None:
    emit(
        {
            "ok": True,
            "tool": "mdf-core",
            "tool_version": TOOL_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
    )


def command_doctor(args: argparse.Namespace) -> None:
    repo = repo_path(args.repo)
    root = git_root(repo)
    initialized = manifest_path(repo).is_file()
    findings = doctor.collect_findings(repo, full=True) if initialized else []
    branch: dict[str, Any] | None = None
    branch_error: str | None = None
    if root == repo:
        try:
            branch = branch_details(current_branch(repo))
        except MDFError as exc:
            branch_error = str(exc)
            findings.append(
                Finding(
                    "branch.invalid",
                    branch_error,
                    severity="error",
                )
            )
    payload = {
        "ok": True,
        "operation": "doctor",
        "repo": str(repo),
        "git_root": str(root) if root else None,
        "is_git_root": root == repo,
        "clean": git_is_clean(repo) if root == repo else None,
        "branch": branch,
        "branch_error": branch_error,
        "initialized": initialized,
        "state": None,
        "normal_workflows_allowed": False,
        "findings": serialize_findings(findings),
    }
    if initialized:
        try:
            payload["state"] = load_manifest(repo).get("state")
        except MDFError:
            payload["state"] = "invalid"
        payload["normal_workflows_allowed"] = (
            payload["state"] == "ready"
            and payload["clean"] is True
            and not findings
        )
    emit(payload)


def command_init(args: argparse.Namespace) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_clean(repo)
    ensure_safe_managed_paths(repo)
    baselines = parse_baselines(args.baseline)
    existing_manifest = manifest_path(repo).is_file()
    latest_release: str | None
    if args.latest_release == "none":
        latest_release = None
    elif stable_semver(args.latest_release) is not None:
        latest_release = args.latest_release
    else:
        raise MDFError(
            "--latest-release must be a stable SemVer or none",
            code="invalid_latest_release",
        )
    files = init_files(
        repo,
        baselines,
        latest_release=latest_release,
    )
    create = [
        relative(repo, path) for path in sorted(files) if not path.exists()
    ]
    update = [relative(repo, path) for path in sorted(files) if path.exists()]
    plan = {
        "mode": "migration" if existing_manifest else "initialization",
        "create": create,
        "update": update,
        "state": "initializing",
        "latest_release": latest_release,
        "baselines": baselines,
        "files": [
            {
                "path": relative(repo, path),
                "action": "update" if path.exists() else "create",
                "diff": text_diff(
                    relative(repo, path),
                    (
                        path.read_text(encoding="utf-8")
                        if path.exists() and path.is_file()
                        else ""
                    ),
                    content,
                ),
            }
            for path, content in sorted(
                files.items(),
                key=lambda item: relative(repo, item[0]),
            )
        ],
        "next": "Write every confirmed documented baseline, set state to ready, then run full validation.",
    }
    if not args.dry_run:
        write_files(
            files,
            replace_allowed={
                path
                for path in (repo / "AGENTS.md", manifest_path(repo))
                if path.exists()
            },
        )
    emit(
        {
            "ok": True,
            "operation": "init",
            "dry_run": args.dry_run,
            "repo": str(repo),
            "plan": plan,
        }
    )


def validation_payload(repo: Path, scope: str) -> tuple[dict[str, Any], int]:
    findings = doctor.collect_findings(repo, full=scope == "full")
    payload = {
        "ok": not findings,
        "operation": "validate",
        "scope": scope,
        "repo": str(repo),
        "finding_count": len(findings),
        "findings": serialize_findings(findings),
    }
    return payload, 0 if not findings else 2


def command_validate(args: argparse.Namespace) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    payload, exit_code = validation_payload(repo, args.scope)
    emit(payload)
    if exit_code:
        raise SystemExit(exit_code)


def command_make_id(args: argparse.Namespace) -> None:
    prefix = "req" if args.type == "requirement" else "bug"
    identifier = f"{prefix}-{new_ulid()}"
    slug = slugify(args.slug)
    emit(
        {
            "ok": True,
            "operation": "make-id",
            "type": args.type,
            "id": identifier,
            "filename": f"{identifier}-{slug}.md",
        }
    )


def command_branch(args: argparse.Namespace) -> None:
    name = args.name
    if name is None:
        if args.repo is None:
            raise MDFError(
                "branch requires --repo or --name", code="missing_argument"
            )
        name = current_branch(repo_path(args.repo))
    emit({"ok": True, "operation": "branch", **branch_details(name)})


def command_semver(args: argparse.Namespace) -> None:
    previous = stable_semver(args.previous)
    candidate = stable_semver(args.candidate)
    if previous is None or candidate is None:
        raise MDFError(
            "Previous and candidate must be stable MAJOR.MINOR.PATCH versions",
            code="invalid_semver",
        )
    raw_categories: list[str] = (
        [part.strip() for part in args.categories.split(",")]
        if args.categories
        else []
    )
    categories = {item for item in raw_categories if item}
    allowed = {
        "Added",
        "Changed",
        "Deprecated",
        "Removed",
        "Fixed",
        "Security",
        "none",
    }
    unknown = sorted(categories - allowed)
    if unknown:
        raise MDFError(
            f"Unknown changelog categories: {', '.join(unknown)}",
            code="bad_category",
        )
    if not categories:
        categories = {"none"}
    if "none" in categories and len(categories) > 1:
        raise MDFError(
            "release_notes none must be exclusive", code="mixed_none"
        )
    actual = bump_kind(previous, candidate)
    removed_without_declaration = "Removed" in categories and not args.breaking
    effective_breaking = args.breaking
    required = required_bump(previous, categories, effective_breaking)
    rank = {"patch": 1, "minor": 2, "major": 3}
    allowed_bump = (
        not removed_without_declaration and rank[actual] >= rank[required]
    )
    payload = {
        "ok": allowed_bump,
        "operation": "semver-check",
        "previous": args.previous,
        "candidate": args.candidate,
        "categories": sorted(categories),
        "breaking": effective_breaking,
        "breaking_declared": args.breaking,
        "removed_requires_breaking": removed_without_declaration,
        "required_bump": required,
        "actual_bump": actual,
    }
    emit(payload)
    if not allowed_bump:
        raise SystemExit(2)


def command_archive(args: argparse.Namespace) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_safe_managed_paths(repo)
    load_manifest(repo)
    ensure_clean(repo)
    input_findings = doctor.collect_findings(repo, full=True)
    if input_findings:
        raise MDFError(
            "Archive input does not pass full validation",
            code="invalid_object",
            details={"findings": serialize_findings(input_findings)},
        )
    moves, rewrites = archive_plan(repo, args.epoch)
    move_details = describe_moves(repo, moves)
    rewrite_details = describe_rewrites(repo, rewrites)
    payload = {
        "ok": True,
        "operation": "archive",
        "dry_run": args.dry_run,
        "epoch": args.epoch,
        "external_links": "not_rewritten",
        "moves": move_details,
        "rewrites": [relative(repo, path) for path in sorted(rewrites)],
        "rewrite_details": rewrite_details,
        "validation": {"scope": "full", "finding_count": 0},
    }
    if not args.dry_run:
        apply_moves_and_rewrites(moves, rewrites)
        post_findings = doctor.collect_findings(repo, full=True)
        if post_findings:
            raise MDFError(
                "Archive post-validation failed; leave the git worktree for manual inspection",
                code="post_validation_failed",
                details={"findings": serialize_findings(post_findings)},
            )
    emit(payload)


def command_move_change(args: argparse.Namespace) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_safe_managed_paths(repo)
    load_manifest(repo)
    ensure_clean(repo)
    source = Path(args.source) if args.source else None
    moves, rewrites, target = change_move_plan(repo, source, args.branch_slug)
    move_details = describe_moves(repo, moves)
    rewrite_details = describe_rewrites(repo, rewrites)
    payload = {
        "ok": True,
        "operation": "move-change",
        "dry_run": args.dry_run,
        "target": relative(repo, target),
        "moves": move_details,
        "rewrites": [relative(repo, path) for path in sorted(rewrites)],
        "rewrite_details": rewrite_details,
    }
    if not args.dry_run:
        if moves:
            apply_moves_and_rewrites(moves, rewrites)
        elif not target.exists():
            target.mkdir(parents=True, exist_ok=False)
    emit(payload)


def command_planning_candidates(args: argparse.Namespace) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    slug = slugify(args.branch_slug)
    candidates = find_planning_candidates(repo, slug)
    state = (
        "none"
        if not candidates
        else "unique" if len(candidates) == 1 else "ambiguous"
    )
    emit(
        {
            "ok": True,
            "operation": "planning-candidates",
            "branch_slug": slug,
            "roots": list(PLANNING_ROOTS),
            "state": state,
            "candidates": [relative(repo, path) for path in candidates],
        }
    )
