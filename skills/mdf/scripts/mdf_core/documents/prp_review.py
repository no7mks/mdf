"""校验未开工 Proposal，在原 Markdown 文件中更新状态。"""
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile

from mdf_core.documents.proposals import check_proposals, started
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.foundation.paths import ensure_safe_managed_paths, load_manifest, relative
from mdf_core.foundation.yamlutil import frontmatter_span, parse_yaml, set_frontmatter_field
from mdf_core.inspection.validate_links import require_existing_local_links
from mdf_core.workspace.gitutil import (
    current_branch, git_directory, git_in_progress_head, repo_path, require_git_root, require_planning,
)
from mdf_core.workspace.merge_policy import configured, git, sha
from mdf_core.workspace.pm import rework_source
from mdf_core.workspace.workflow_policy import is_github_flow


def command_prp_review(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    github = is_github_flow(repo)
    action = args.action
    if not github and action in {"prepare", "commit"}:
        raise MDFError("prp-review prepare 与 commit 仅用于 github-flow", code="invalid_workflow")
    if github and action != "check":
        from mdf_core.lifecycle.pull_finish import finish_lock
        with finish_lock(repo):
            require_review_idle(repo)
            review(args, repo, github)
        return
    review(args, repo, github)


def require_review_idle(repo):
    git_dir = git_directory(repo)
    if git_in_progress_head(repo) or any(
        (git_dir / name).exists() for name in ("rebase-merge", "rebase-apply", "sequencer", "BISECT_START")
    ):
        raise MDFError("请先完成当前 Git 操作", code="dirty_worktree")


def review(args, repo, github):
    branch = current_branch(repo)
    pm_revision = github and configured(repo)["mode"] == "pr" and rework_source(repo, branch)
    if not (pm_revision or (github and branch.startswith("adhoc/"))):
        require_planning(repo)
    ensure_safe_managed_paths(repo)
    if load_manifest(repo).get("state") != "ready":
        raise MDFError("prp-review 需要 ready 仓库", code="manifest_not_ready")

    objects = check_proposals(repo)
    if args.proposal not in objects:
        raise MDFError("缺少指定 PRP", code="missing_proposal")
    path, metadata, _ = objects[args.proposal]
    if path.parent != repo / "docs/proposals" or started(repo, args.proposal):
        raise MDFError("仅未开工 active PRP 可以评审", code="proposal_started")

    action = args.action
    relpath = relative(repo, path)
    result = {"ok": True, "operation": "prp-review", "action": action, "path": relpath}
    if action == "prepare" and metadata.get("status") not in {"draft", "ready"}:
        raise MDFError("仅 draft 或 ready PRP 可以准备评审", code="invalid_proposal_state")
    if github and action in {"prepare", "draft"}:
        if git(repo, "--literal-pathspecs", "status", "--porcelain", "--", relpath).stdout:
            raise MDFError("目标 PRP 已有未提交改动，请先核对", code="review_target_dirty", details={"path": relpath})
        if action == "prepare":
            emit(result)
            return
    if github and action in {"ready", "commit"}:
        staged = git(repo, "--literal-pathspecs", "diff", "--cached", "--name-only", "--", relpath)
        if staged.stdout:
            raise MDFError("目标 PRP 已有暂存改动，请先核对", code="review_target_dirty", details={"path": relpath})

    original = path.read_bytes()
    text = original.decode("utf-8")
    start, end, _ = frontmatter_span(text)
    metadata = parse_yaml(text[start:end])
    status = metadata.get("status")
    expected = "ready" if action in {"draft", "commit"} else "draft"
    if status != expected and not (github and action == "check" and status == "ready"):
        raise MDFError(f"本操作需要 {expected} PRP", code="invalid_proposal_state")
    require_existing_local_links(repo, [path])
    if action == "commit":
        if not args.ready_sha256 or not args.message:
            raise MDFError("提交须传确认的 --ready-sha256 与 --message", code="invalid_arguments")
        if hashlib.sha256(original).hexdigest() != args.ready_sha256:
            raise MDFError("ready 稿件已变化，须重新确认", code="review_changed")
        if not git(repo, "--literal-pathspecs", "ls-tree", "--name-only", "HEAD", "--", relpath).stdout:
            raise MDFError("目标 PRP 尚未提交，请先核对", code="review_target_dirty", details={"path": relpath})
        diff = git(repo, "--literal-pathspecs", "diff", "--name-only", "HEAD", "--", relpath)
        committed = bool(diff.stdout)
        if committed:
            git(repo, "--literal-pathspecs", "commit", "--only", "-m", args.message, "--", relpath)
        emit({**result, "head": sha(repo, "HEAD"), "committed": committed})
        return
    if action in {"check", "ready"}:
        digest = hashlib.sha256(original).hexdigest()
        if action == "check":
            if github:
                result["status"] = status
            emit({**result, "sha256": digest})
            return
        if not args.confirmed_sha256:
            raise MDFError("ready 前须取得用户确认并传 --confirmed-sha256", code="confirmation_required")
        if args.confirmed_sha256 != digest:
            raise MDFError("Markdown 稿件已变化，须重新确认", code="review_changed")

    content = set_frontmatter_field(text, "status", action).encode("utf-8")
    candidate = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".prp-review-", delete=False) as stream:
            candidate = Path(stream.name)
            stream.write(content)
        candidate.chmod(path.stat().st_mode)
        if path.read_bytes() != original:
            raise MDFError("Markdown 稿件已变化，须重新确认", code="review_changed")
        candidate.replace(path)
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)
    emit({**result, "sha256": hashlib.sha256(content).hexdigest()} if github and action == "ready" else result)
