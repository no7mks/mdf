"""非 feature 审查的全量验证及内容绑定证据。"""
from .closeout_validate import run_verify_commands
from .delivery_state import inventory, digest, git, safe, write_json, read_json
from .errors import MDFError, emit
from .gitutil import current_branch, branch_details, repo_path, require_git_root
from .paths import load_manifest
from .verification import manifest_items


def inputs(repo, items):
    files = {name: value for name, value in inventory(repo).items()
             if not name.startswith(("docs/", "changes/"))
             and not ("/" not in name and name.endswith(".md")) and name != ".mdf/manifest.yaml"}
    return digest([files, items])


def command_project_verify(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    branch = current_branch(repo)
    if branch_details(branch)["kind"] not in {"bugfix", "hotfix", "release"}:
        raise MDFError("此验证入口只用于非 feature 交付", code="stage_branch")
    manifest = load_manifest(repo)
    if manifest.get("state") != "ready":
        raise MDFError("验证需要 ready", code="manifest_not_ready")
    items = manifest_items(manifest)
    before = inputs(repo, items)
    path = safe(repo, repo / "docs/context/research/code-review" / f"{branch}.verification.json")
    if args.action == "check":
        result = read_json(path)
        if result.get("inputs") != before or result.get("branch") != branch or not result.get("all_passed"):
            raise MDFError("全量验证失败或证据过期", code="stale_verification")
    else:
        results = []
        for item in items:
            try:
                detail = run_verify_commands(repo, [item["command"]])[0]
                results.append({**item, **detail, "passed": True})
            except MDFError as exc:
                results.append({**item, "passed": False, "error": exc.code, "details": exc.details})
        after = inputs(repo, manifest_items(load_manifest(repo)))
        result = {"branch": branch, "inputs": before, "head": git(repo, "rev-parse", "HEAD").stdout.strip(),
                  "results": results, "all_passed": before == after and all(item["passed"] for item in results)}
        write_json(path, result)
        if not result["all_passed"]:
            raise MDFError("全量验证失败或输入变化", code="verify_command_failed", details=result)
    emit({"ok": True, "operation": f"project-verify-{args.action}", "result": result})
