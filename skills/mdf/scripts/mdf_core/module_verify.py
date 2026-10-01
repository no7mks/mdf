"""`$mdf` CLI 的 module 级 verify：on-site 与 full。"""
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
from .modules import load_modules
from .modules_check import module_commands
from .paths import load_manifest
from .project_verify import associated_suites, run_targets
from .verification import (
    STEPS,
    required_suite,
    required_suites,
    suites_cover,
    recorded_suites,
)


def evidence_file(repo: Path, slug: str) -> Path:
    return safe(
        repo,
        repo / "changes/unreleased" / slug / "verify.full.json",
    )


def _delivery_slug(repo: Path) -> tuple[str, str, str]:
    branch = current_branch(repo)
    details = branch_details(branch)
    kind = details["kind"]
    if kind not in {"feature", "bugfix", "hotfix", "release"}:
        raise MDFError("verify 需要 Gitflow 交付分支", code="stage_branch")
    return branch, kind, unreleased_slug(details)


def plan_full(repo: Path, kind: str) -> list[dict[str, Any]]:
    from .verification import repo_verification

    suite = required_suite(kind)
    return repo_verification(repo).plan(suite)


def plan_onsite(repo: Path, modules: list[str]) -> list[dict[str, Any]]:
    config = load_modules(repo)
    if not modules:
        raise MDFError("on-site 必须指定至少一个 module", code="verify_modules")
    for name in modules:
        config.get(name)
    targets: list[dict[str, Any]] = []
    for entry in (*STEPS, "quick"):
        targets.extend(module_commands(config, modules, entry))
    return targets


def valid_full(repo: Path) -> dict[str, Any] | None:
    """已落盘且声称通过的 full 报告；不对照 HEAD / commit。"""
    branch, kind, slug = _delivery_slug(repo)
    path = evidence_file(repo, slug)
    if not path.is_file():
        return None
    result = read_json(path)
    if (
        result.get("branch") != branch
        or result.get("level") != "full"
        or not suites_cover(recorded_suites(result), required_suites(kind))
        or not result.get("all_passed")
    ):
        return None
    return result


def command_verify(args) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    manifest = load_manifest(repo)
    if manifest.get("state") != "ready":
        raise MDFError("verify 需要 ready", code="manifest_not_ready")
    level = args.level
    action = args.action
    if action != "run":
        raise MDFError("verify 只支持 run", code="invalid_verify_action")
    branch, kind, slug = _delivery_slug(repo)
    if level == "full":
        _verify_full(repo, branch, kind, slug)
    else:
        _verify_onsite(repo, branch, kind, slug, args)


def _verify_full(repo, branch, kind, slug) -> None:
    path = evidence_file(repo, slug)
    ensure_clean(repo)
    if kind == "bugfix" and not associated_suites(repo, slug):
        raise MDFError(
            "bugfix 必须在 suites.json 关联 named suite",
            code="missing_delivery_suite",
        )
    targets = plan_full(repo, kind)
    results = run_targets(repo, targets)
    passed = {item["id"] for item in results if item["passed"]}
    expected = {item["id"] for item in targets}
    result = {
        "level": "full",
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
    emit({"ok": True, "operation": "verify-full-run", "result": result})


def _verify_onsite(repo, branch, kind, slug, args) -> None:
    modules = list(args.module or [])
    if args.paths:
        config = load_modules(repo)
        modules = sorted(
            set(modules) | set(config.modules_for_paths(repo, list(args.paths)))
        )
    targets = plan_onsite(repo, modules)
    # 额外 test/testcase 命令由 Agent 经 suite-run / run 执行；此处只跑 lint+build+quick
    results = run_targets(repo, targets)
    extra = list(args.test or [])
    for index, command in enumerate(extra, 1):
        from .verify_run import run_verify_command

        try:
            detail = run_verify_command(
                repo,
                command,
                label=f"onsite-test-{index}",
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
        "level": "on-site",
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
            "on-site 验证失败",
            code="verify_command_failed",
            details=result,
        )
    emit({"ok": True, "operation": "verify-onsite-run", "result": result})
