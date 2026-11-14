"""PRP review 生成物与唯一持久化格式转换；确认由 Agent 取得。"""
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.workspace.gitutil import current_branch, repo_path, require_git_root, require_planning
from mdf_core.workspace.merge_policy import configured
from mdf_core.workspace.pm import outside_pm_paths, rework_source
from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch
from mdf_core.documents.html_documents import render_html, update_metadata
from mdf_core.documents.moves import replacement_plan
from mdf_core.foundation.paths import ensure_safe_managed_paths, load_manifest, relative
from mdf_core.documents.proposals import check_proposals, started
from mdf_core.documents.prp_split import render
from mdf_core.inspection.validate_links import require_existing_local_links


def command_prp_format(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    github = is_github_flow(repo)
    branch = current_branch(repo)
    trunk = trunk_branch(repo)
    pm_revision = github and configured(repo)["mode"] == "pr" and rework_source(repo, branch)
    delivery = github and branch.startswith("adhoc/")
    if not (pm_revision or delivery):
        require_planning(repo)
    ensure_safe_managed_paths(repo)
    if load_manifest(repo).get("state") != "ready":
        raise MDFError("prp-format 需要 ready 仓库", code="manifest_not_ready")
    objects = check_proposals(repo)
    if args.proposal not in objects:
        raise MDFError("缺少指定 PRP", code="missing_proposal")
    path, metadata, body = objects[args.proposal]
    if len(path.relative_to(repo / "docs").parts) != 2 or started(repo, args.proposal):
        raise MDFError("仅未开工 active PRP 可以转换", code="proposal_started")
    action = args.action
    to_draft = action == "draft" or (action == "plan" and metadata.get("status") == "ready")
    expected = "ready" if to_draft else "draft"
    if metadata.get("status") != expected:
        raise MDFError(f"本操作需要 {expected} PRP", code="invalid_proposal_state")
    require_existing_local_links(repo, [path])
    preview = path.with_suffix(".review.html")
    if action == "preview":
        if preview.is_symlink():
            raise MDFError("review HTML 不得为 symlink", code="unsafe_path")
        preview.write_text(render_html(metadata, body), encoding="utf-8")
        emit({"ok": True, "operation": "prp-format", "action": action, "path": relative(repo, preview)})
        return
    target = path.with_suffix(".md" if to_draft else ".html")
    if target != path and target.exists():
        raise MDFError("目标 PRP 路径已存在", code="collision")
    rewrites = replacement_plan(repo, {path: target})
    changed = sorted({relative(repo, item) for item in (path, target, *rewrites)})
    outside = outside_pm_paths(changed)
    if action == "plan":
        emit({"ok": True, "operation": "prp-format", "action": action, "paths": changed, "outside_pm": outside})
        return
    if github and (branch == trunk or pm_revision) and outside:
        raise MDFError("Proposal 格式转换须在普通 adhoc 交付中完成",
                       code="proposal_requires_delivery", details={"paths": outside})
    if preview.is_symlink():
        raise MDFError("review HTML 不得为 symlink", code="unsafe_path")
    if args.action == "ready":
        if not args.confirmed:
            raise MDFError("ready 前必须取得用户明确确认并传 --confirmed", code="confirmation_required")
        if not preview.is_file() or preview.read_text() != render_html(metadata, body):
            raise MDFError("review HTML 缺失或 draft 已变化；重新生成并确认", code="preview_changed")
        content = update_metadata(preview.read_text(), {**metadata, "status": "ready"})
    else:
        content = render({**metadata, "status": "draft"}, body)
    before = {item: item.read_bytes() for item in {path, *rewrites}}
    try:
        target.write_text(content, encoding="utf-8")
        # 同一对象指向自身旧路径时，转换后的 HTML / Markdown 也须改写。
        converted_rewrites = replacement_plan(repo, {path: target})
        if target in converted_rewrites:
            target.write_text(converted_rewrites[target], encoding="utf-8")
        if target != path:
            path.unlink()
        for item, text in rewrites.items():
            if item != path:
                item.write_text(text, encoding="utf-8")
        check_proposals(repo)
        require_existing_local_links(repo, [target, *[item for item in rewrites if item != path]])
    except (OSError, MDFError):
        if target != path:
            target.unlink(missing_ok=True)
        for item, data in before.items():
            item.write_bytes(data)
        raise
    preview.unlink(missing_ok=True)
    emit({"ok": True, "operation": "prp-format", "action": args.action, "path": relative(repo, target),
          "rewrites": [relative(repo, item) for item in rewrites if item != path]})
