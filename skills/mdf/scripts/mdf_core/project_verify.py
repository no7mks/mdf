"""非 feature 审查验证；full 证据以 commit 为锚（见 module_verify）。"""
from .verify_run import run_verify_command
from .delivery_state import git, safe, write_json, read_json
from .errors import MDFError, emit
from .gitutil import (
    current_branch,
    branch_details,
    repo_path,
    require_git_root,
    unreleased_slug,
    ensure_clean,
)
from .paths import load_manifest
from .verification import (
    SUITES,
    repo_verification,
    parse_suite_names,
    recorded_suites,
    required_suite,
    required_suites,
    suites_cover,
)


def associated_suites(repo, slug):
    path = repo / "changes/unreleased" / slug / "suites.json"
    if not path.is_file():
        return None
    data = read_json(safe(repo, path))
    if not isinstance(data, dict) or set(data) != {"suites"}:
        raise MDFError(
            "suites.json 只接受 suites 列表", code="invalid_delivery_suite"
        )
    return parse_suite_names(data["suites"])


def evidence_path(repo):
    branch = current_branch(repo)
    details = branch_details(branch)
    slug = unreleased_slug(details)
    return safe(
        repo,
        repo / "changes/unreleased" / slug / "verify.full.json",
    )


def valid_evidence(repo):
    """当前 HEAD commit 上仍有效的 full 全绿证据。"""
    from .module_verify import valid_full

    return valid_full(repo)


def run_targets(repo, targets):
    """全部运行，不因单项失败中断；每项带 passed 与失败 error/details。"""
    results = []
    total = len(targets)
    for index, item in enumerate(targets, 1):
        try:
            detail = run_verify_command(
                repo,
                item["command"],
                label=item["id"],
                index=index,
                total=total,
                timeout=item.get("budget"),
                entry=item.get("entry", item["id"]),
                junit=item.get("entry", item["id"]) in SUITES
                or item["id"].split(":")[-1] in SUITES,
            )
            results.append({**item, **detail, "passed": True})
        except MDFError as exc:
            results.append(
                {
                    **item,
                    "passed": False,
                    "error": exc.code,
                    "details": exc.details,
                }
            )
    return results


def command_quick_run(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    manifest = load_manifest(repo)
    if manifest.get("state") != "ready":
        raise MDFError("quick-run 需要 ready", code="manifest_not_ready")
    results = run_targets(repo, repo_verification(repo).plan("quick"))
    result = {
        "head": git(repo, "rev-parse", "HEAD").stdout.strip(),
        "results": results,
        "all_passed": all(item["passed"] for item in results),
    }
    if not result["all_passed"]:
        raise MDFError(
            "lint、build 或 quick 失败",
            code="verify_command_failed",
            details=result,
        )
    emit({"ok": True, "operation": "quick-run", "result": result})


def command_project_verify(args):
    """兼容入口：等价于 `verify full`。"""
    from .module_verify import command_verify
    import argparse

    ns = argparse.Namespace(
        repo=args.repo,
        level="full",
        action=args.action,
        module=[],
        paths=[],
        test=[],
    )
    command_verify(ns)


def command_suite_run(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    name = parse_suite_names([args.name])[0]
    result = run_verify_command(
        repo, args.command, label=name, entry=name, junit=True
    )
    emit({"ok": True, "operation": "suite-run", "result": result})
