"""`$mdf` CLI 的 module 级 verify：smart / branch / named。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .delivery_state import safe, write_json, read_json
from .errors import MDFError, emit
from .gitutil import (
    branch_details,
    current_branch,
    ensure_clean,
    repo_path,
    require_git_root,
    unreleased_slug,
)
from .modules import SUITE_DOC_DIR, load_modules
from .modules_check import module_commands
from .paths import load_manifest
from .project_verify import associated_suites, run_targets
from .verification import (
    ENTRIES,
    NAME_RE,
    RESERVED,
    STEPS,
    SUITES,
    parse_named_commands,
    required_suite,
    required_suites,
    suites_cover,
    recorded_suites,
)
from .yamlutil import read_frontmatter


def evidence_file(repo: Path, slug: str) -> Path:
    return safe(
        repo,
        repo / "changes/unreleased" / slug / "verify.branch.json",
    )


def _delivery_slug(repo: Path) -> tuple[str, str, str]:
    branch = current_branch(repo)
    details = branch_details(branch)
    kind = details["kind"]
    if kind not in {"feature", "bugfix", "hotfix", "release"}:
        raise MDFError("verify 需要 Gitflow 交付分支", code="stage_branch")
    return branch, kind, unreleased_slug(details)


def plan_branch(repo: Path, kind: str) -> list[dict[str, Any]]:
    from .verification import repo_verification

    suite = required_suite(kind)
    return repo_verification(repo).plan(suite)


def plan_smart(repo: Path, modules: list[str]) -> list[dict[str, Any]]:
    config = load_modules(repo)
    if not modules:
        raise MDFError("smart 必须指定至少一个 module", code="verify_modules")
    for name in modules:
        config.get(name)
    targets: list[dict[str, Any]] = []
    for entry in (*STEPS, "quick"):
        targets.extend(module_commands(config, modules, entry))
    return targets


def entry_parallel(repo: Path, entry: str) -> bool:
    """五固定入口是否并行；lint/build 与 override 单命令为 False。"""
    config = load_modules(repo)
    if entry in config.overrides or entry in STEPS:
        return False
    if entry not in SUITES:
        return False
    return any(config.get(name).suite(entry).parallel for name in config.names())


def resolve_named_suite(repo: Path, name: str) -> tuple[list[dict[str, Any]], bool]:
    """解析单个 suite 名为 targets + parallel。"""
    if name in ENTRIES:
        from .verification import repo_verification

        targets = repo_verification(repo)._items_for_entry(name)
        return targets, entry_parallel(repo, name)
    if (
        not isinstance(name, str)
        or not NAME_RE.fullmatch(name)
        or name in RESERVED
    ):
        raise MDFError(
            f"suite 名称无效或保留: {name}",
            code="invalid_delivery_suite",
        )
    owners = load_modules(repo).named_owner()
    if name not in owners:
        raise MDFError(
            f"未知 named suite: {name}",
            code="unknown_named_suite",
        )
    path = repo / SUITE_DOC_DIR / f"{name}.md"
    if not path.is_file():
        raise MDFError(
            f"缺少 named suite 文档 {SUITE_DOC_DIR}/{name}.md",
            code="missing_named_suite_doc",
        )
    meta, _ = read_frontmatter(path)
    commands, parallel = parse_named_commands(meta)
    targets = [
        {
            "id": name if len(commands) == 1 else f"{name}:{index}",
            "entry": name,
            "command": command,
            "budget": None,
            "junit": True,
        }
        for index, command in enumerate(commands, 1)
    ]
    return targets, parallel


def parse_suites_arg(raw: str | None) -> list[str]:
    if raw is None or not str(raw).strip():
        raise MDFError(
            "named 需要 --suites",
            code="verify_suites",
        )
    names = [part.strip() for part in str(raw).split(",") if part.strip()]
    if not names:
        raise MDFError("named 需要 --suites", code="verify_suites")
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise MDFError(
                f"suite 名称重复: {name}",
                code="invalid_delivery_suite",
            )
        seen.add(name)
    return names


def valid_branch(repo: Path) -> dict[str, Any] | None:
    """已落盘且声称通过的 branch 报告；不对照 HEAD / commit。"""
    branch, kind, slug = _delivery_slug(repo)
    path = evidence_file(repo, slug)
    if not path.is_file():
        return None
    result = read_json(path)
    if (
        result.get("branch") != branch
        or result.get("level") != "branch"
        or not suites_cover(recorded_suites(result), required_suites(kind))
        or not result.get("all_passed")
    ):
        return None
    return result


# 兼容旧名引用
valid_full = valid_branch
plan_full = plan_branch
plan_onsite = plan_smart


def command_verify(args) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    manifest = load_manifest(repo)
    if manifest.get("state") != "ready":
        raise MDFError("verify 需要 ready", code="manifest_not_ready")
    scope = getattr(args, "scope", None) or getattr(args, "level", None)
    action = args.action
    if action != "run":
        raise MDFError("verify 只支持 run", code="invalid_verify_action")
    if scope == "named":
        _verify_named(repo, args)
        return
    if getattr(args, "suites", None):
        raise MDFError(
            "--suites 仅用于 --scope named",
            code="invalid_verify_scope",
        )
    branch, kind, slug = _delivery_slug(repo)
    if scope == "branch":
        _verify_branch(repo, branch, kind, slug)
    elif scope == "smart":
        _verify_smart(repo, branch, kind, slug, args)
    else:
        raise MDFError(
            "verify --scope 须为 smart、branch 或 named",
            code="invalid_verify_scope",
        )


def _run_entry_groups(repo: Path, kind: str | None = None) -> list[dict[str, Any]]:
    """branch：按 lint→build→quick→smoke|release 分组，组内可并行。"""
    from .verification import repo_verification

    suite = required_suite(kind) if kind else "quick"
    names = [*STEPS, "quick"] + ([suite] if suite != "quick" else [])
    verification = repo_verification(repo)
    groups: list[tuple[list[dict[str, Any]], bool]] = []
    for entry in names:
        items = verification._items_for_entry(entry)
        groups.append((items, entry_parallel(repo, entry)))
    grand_total = sum(len(items) for items, _ in groups)
    results: list[dict[str, Any]] = []
    offset = 0
    for items, parallel in groups:
        results.extend(
            run_targets(
                repo,
                items,
                parallel=parallel,
                index_base=offset,
                grand_total=grand_total,
            )
        )
        offset += len(items)
    return results


def _verify_branch(repo, branch, kind, slug) -> None:
    path = evidence_file(repo, slug)
    ensure_clean(repo)
    if kind == "bugfix" and not associated_suites(repo, slug):
        raise MDFError(
            "bugfix 必须在 suites.json 关联 named suite",
            code="missing_delivery_suite",
        )
    results = _run_entry_groups(repo, kind)
    expected = {item["id"] for item in plan_branch(repo, kind)}
    passed = {item["id"] for item in results if item["passed"]}
    result = {
        "level": "branch",
        "branch": branch,
        "kind": kind,
        "modules": load_modules(repo).names(),
        "suites": required_suites(kind),
        "results": results,
        "all_passed": passed == expected,
    }
    write_json(path, result)
    if not result["all_passed"]:
        raise MDFError(
            "所需 suite 失败",
            code="verify_command_failed",
            details=result,
        )
    emit({"ok": True, "operation": "verify-branch-run", "result": result})


def _verify_smart(repo, branch, kind, slug, args) -> None:
    modules = list(args.module or [])
    if args.paths:
        config = load_modules(repo)
        modules = sorted(
            set(modules) | set(config.modules_for_paths(repo, list(args.paths)))
        )
    # 按入口分组：lint/build 串行组；quick 可并行
    config = load_modules(repo)
    if not modules:
        raise MDFError("smart 必须指定至少一个 module", code="verify_modules")
    results: list[dict[str, Any]] = []
    groups: list[tuple[list[dict[str, Any]], bool]] = []
    for entry in (*STEPS, "quick"):
        items = module_commands(config, modules, entry)
        groups.append((items, entry_parallel(repo, entry)))
    grand_total = sum(len(items) for items, _ in groups)
    offset = 0
    for items, parallel in groups:
        results.extend(
            run_targets(
                repo,
                items,
                parallel=parallel,
                index_base=offset,
                grand_total=grand_total,
            )
        )
        offset += len(items)
    extra = list(args.test or [])
    for index, command in enumerate(extra, 1):
        from .verify_run import run_verify_command

        try:
            detail = run_verify_command(
                repo,
                command,
                label=f"smart-test-{index}",
                index=index,
                total=len(extra),
                junit=False,
            )
            results.append(
                {
                    "id": f"test:{index}",
                    "command": command,
                    "passed": True,
                    **detail,
                }
            )
        except MDFError as exc:
            results.append(
                {
                    "id": f"test:{index}",
                    "command": command,
                    "passed": False,
                    "error": exc.code,
                    "details": exc.details,
                }
            )
    all_passed = all(item["passed"] for item in results)
    result = {
        "level": "smart",
        "branch": branch,
        "kind": kind,
        "modules": modules,
        "named_suites": {
            name: load_modules(repo).named_owner().get(name)
            for module_name in modules
            for name in load_modules(repo).get(module_name).named
        },
        "results": results,
        "all_passed": all_passed,
        "selection_hint": {
            "named_suites": [
                name
                for module_name in modules
                for name in load_modules(repo).get(module_name).named
            ],
            "paths": list(args.paths or []),
        },
    }
    if not all_passed:
        raise MDFError(
            "smart 验证失败",
            code="verify_command_failed",
            details=result,
        )
    emit({"ok": True, "operation": "verify-smart-run", "result": result})


def _verify_named(repo, args) -> None:
    if getattr(args, "module", None) or getattr(args, "paths", None):
        raise MDFError(
            "named 不接受 --module / --paths",
            code="invalid_verify_scope",
        )
    if getattr(args, "test", None):
        raise MDFError(
            "named 不接受 --test",
            code="invalid_verify_scope",
        )
    names = parse_suites_arg(getattr(args, "suites", None))
    results: list[dict[str, Any]] = []
    for name in names:
        targets, parallel = resolve_named_suite(repo, name)
        results.extend(run_targets(repo, targets, parallel=parallel))
    all_passed = all(item["passed"] for item in results)
    result = {
        "level": "named",
        "suites": names,
        "results": results,
        "all_passed": all_passed,
    }
    if not all_passed:
        raise MDFError(
            "named suite 失败",
            code="verify_command_failed",
            details=result,
        )
    emit({"ok": True, "operation": "verify-named-run", "result": result})
