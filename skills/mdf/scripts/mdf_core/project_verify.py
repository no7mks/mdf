"""非 feature 审查的验证及内容绑定证据。"""
from .closeout_validate import run_verify_commands
from .delivery_state import inventory, digest, git, safe, write_json, read_json
from .errors import MDFError, emit
from .gitutil import (
    current_branch, branch_details, repo_path, require_git_root, unreleased_slug,
)
from .paths import load_manifest
from .verification import (
    collections_cover, is_layered, manifest_items, parse_suite_names,
    recorded_collections, required_collections, select_items,
)


def associated_suites(repo, slug):
    path = repo / "changes/unreleased" / slug / "suites.json"
    if not path.is_file():
        return None
    data = read_json(safe(repo, path))
    if not isinstance(data, dict) or set(data) != {"suites"}:
        raise MDFError("suites.json 只接受 suites 列表", code="invalid_delivery_suite")
    return parse_suite_names(data["suites"])


def inputs(repo, items, required, suites):
    files = {name: value for name, value in inventory(repo).items()
             if not name.startswith(("docs/", "changes/"))
             and not ("/" not in name and name.endswith(".md")) and name != ".mdf/manifest.yaml"}
    return digest([files, items, required, suites])


def command_project_verify(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    branch = current_branch(repo)
    details = branch_details(branch)
    kind = details["kind"]
    if kind not in {"bugfix", "hotfix", "release"}:
        raise MDFError("此验证入口只用于非 feature 交付", code="stage_branch")
    manifest = load_manifest(repo)
    if manifest.get("state") != "ready":
        raise MDFError("验证需要 ready", code="manifest_not_ready")
    items = manifest_items(manifest)
    slug = unreleased_slug(details)
    suites = associated_suites(repo, slug) if kind == "bugfix" else None
    if kind == "bugfix" and is_layered(items) and not suites:
        raise MDFError("分层后 bugfix 必须关联已有交付 suite", code="missing_delivery_suite")
    required = required_collections(kind, items, suites)
    targets = select_items(items, required)
    before = inputs(repo, items, required, suites)
    path = safe(
        repo,
        repo / "changes/unreleased" / slug / "code-review.verification.json",
    )
    if args.action == "check":
        result = read_json(path)
        recorded = recorded_collections(result, items)
        if (result.get("inputs") != before or result.get("branch") != branch
                or not collections_cover(recorded, required)
                or not result.get("all_passed")):
            raise MDFError("所需验证集合失败或证据过期", code="stale_verification")
    else:
        results = []
        for item in targets:
            try:
                detail = run_verify_commands(repo, [item["command"]])[0]
                results.append({**item, **detail, "passed": True})
            except MDFError as exc:
                results.append({**item, "passed": False, "error": exc.code, "details": exc.details})
        after_items = manifest_items(load_manifest(repo))
        after_suites = associated_suites(repo, slug) if kind == "bugfix" else None
        after = inputs(repo, after_items, required, after_suites)
        passed = {item["id"] for item in results if item["passed"]}
        expected = {item["id"] for item in targets}
        result = {
            "branch": branch, "collections": required, "inputs": before,
            "head": git(repo, "rev-parse", "HEAD").stdout.strip(),
            "results": results,
            "all_passed": before == after and passed == expected,
        }
        write_json(path, result)
        if not result["all_passed"]:
            raise MDFError("所需验证集合失败或输入变化", code="verify_command_failed", details=result)
    emit({"ok": True, "operation": f"project-verify-{args.action}", "result": result})
