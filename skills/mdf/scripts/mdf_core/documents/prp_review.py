"""校验未开工 Proposal，在原 Markdown 文件中更新状态。"""
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile

from mdf_core.documents.proposals import check_proposals, started
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.foundation.paths import ensure_safe_managed_paths, load_manifest, relative
from mdf_core.foundation.yamlutil import frontmatter_span, parse_yaml, set_frontmatter_field
from mdf_core.inspection.validate_links import require_existing_local_links
from mdf_core.workspace.gitutil import current_branch, repo_path, require_git_root, require_planning
from mdf_core.workspace.merge_policy import configured
from mdf_core.workspace.pm import rework_source
from mdf_core.workspace.workflow_policy import is_github_flow


def command_prp_review(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    branch = current_branch(repo)
    github = is_github_flow(repo)
    pm_revision = github and configured(repo)["mode"] == "pr" and rework_source(repo, branch)
    if not (pm_revision or (github and branch.startswith("adhoc/"))):
        require_planning(repo)
    ensure_safe_managed_paths(repo)
    if load_manifest(repo).get("state") != "ready":
        raise MDFError("prp-review 需要 ready 仓库", code="manifest_not_ready")

    objects = check_proposals(repo)
    if args.proposal not in objects:
        raise MDFError("缺少指定 PRP", code="missing_proposal")
    path, _, _ = objects[args.proposal]
    if path.parent != repo / "docs/proposals" or started(repo, args.proposal):
        raise MDFError("仅未开工 active PRP 可以评审", code="proposal_started")

    original = path.read_bytes()
    text = original.decode("utf-8")
    start, end, _ = frontmatter_span(text)
    metadata = parse_yaml(text[start:end])
    action = args.action
    expected = "ready" if action == "draft" else "draft"
    if metadata.get("status") != expected:
        raise MDFError(f"本操作需要 {expected} PRP", code="invalid_proposal_state")
    require_existing_local_links(repo, [path])
    result = {"ok": True, "operation": "prp-review", "action": action, "path": relative(repo, path)}
    if action in {"check", "ready"}:
        digest = hashlib.sha256(original).hexdigest()
        if action == "check":
            emit({**result, "sha256": digest})
            return
        if not args.confirmed_sha256:
            raise MDFError("ready 前须取得用户确认并传 --confirmed-sha256", code="confirmation_required")
        if args.confirmed_sha256 != digest:
            raise MDFError("Markdown 稿件已变化，须重新确认", code="review_changed")

    content = set_frontmatter_field(text, "status", action)
    candidate = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".prp-review-", delete=False) as stream:
            candidate = Path(stream.name)
            stream.write(content.encode("utf-8"))
        candidate.chmod(path.stat().st_mode)
        if path.read_bytes() != original:
            raise MDFError("Markdown 稿件已变化，须重新确认", code="review_changed")
        candidate.replace(path)
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)
    emit(result)
