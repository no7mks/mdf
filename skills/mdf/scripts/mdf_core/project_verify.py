"""非 feature 审查的验证及内容绑定证据。"""
from .verify_run import run_verify_command
from .delivery_state import inventory, digest, git, safe, write_json, read_json
from .errors import MDFError, emit
from .gitutil import (
    current_branch, branch_details, repo_path, require_git_root, unreleased_slug,
)
from .paths import load_manifest
from .verification import manifest_verification, parse_suite_names, suites_cover


def associated_suites(repo, slug):
    path = repo / "changes/unreleased" / slug / "suites.json"
    if not path.is_file():
        return None
    data = read_json(safe(repo, path))
    if not isinstance(data, dict) or set(data) != {"suites"}:
        raise MDFError("suites.json 只接受 suites 列表", code="invalid_delivery_suite")
    return parse_suite_names(data["suites"])


def inputs(repo, verification, required, suites):
    files = {name: value for name, value in inventory(repo).items()
             if not name.startswith(("docs/", "changes/"))
             and not ("/" not in name and name.endswith(".md")) and name != ".mdf/manifest.yaml"}
    return digest([files, verification.items, verification.suites, required, suites])


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
    verification = manifest_verification(manifest)
    slug = unreleased_slug(details)
    suites = associated_suites(repo, slug) if kind == "bugfix" else None
    if kind == "bugfix" and verification.layered and not suites:
        raise MDFError("分层后 bugfix 必须关联已有交付 suite", code="missing_delivery_suite")
    required = verification.required(kind, suites)
    targets = verification.select(required)
    before = inputs(repo, verification, required, suites)
    path = safe(
        repo,
        repo / "changes/unreleased" / slug / "code-review.verification.json",
    )
    if args.action == "check":
        result = read_json(path)
        recorded = verification.recorded(result)
        if (result.get("inputs") != before or result.get("branch") != branch
                or not suites_cover(recorded, required)
                or not result.get("all_passed")):
            raise MDFError("所需 suite 失败或证据过期", code="stale_verification")
    else:
        results = []
        planned = list(targets)
        total = len(planned)
        for index, item in enumerate(planned, 1):
            try:
                detail = run_verify_command(
                    repo,
                    item["command"],
                    label=item["id"],
                    index=index,
                    total=total,
                )
                results.append({**item, **detail, "passed": True})
            except MDFError as exc:
                results.append({
                    **item, "passed": False, "error": exc.code,
                    "details": exc.details,
                })
        after_suites = associated_suites(repo, slug) if kind == "bugfix" else None
        after = inputs(repo, manifest_verification(load_manifest(repo)), required, after_suites)
        passed = {item["id"] for item in results if item["passed"]}
        expected = {item["id"] for item in targets}
        result = {
            "branch": branch, "suites": required, "inputs": before,
            "head": git(repo, "rev-parse", "HEAD").stdout.strip(),
            "results": results,
            "all_passed": before == after and passed == expected,
        }
        write_json(path, result)
        if not result["all_passed"]:
            raise MDFError("所需 suite 失败或输入变化", code="verify_command_failed", details=result)
    emit({"ok": True, "operation": f"project-verify-{args.action}", "result": result})
