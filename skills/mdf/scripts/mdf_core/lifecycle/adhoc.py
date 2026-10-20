"""Adhoc 的固定 objectives 与无 PRP 收口。"""
import re
from pathlib import Path

from mdf_core.foundation.errors import MDFError

STEPS = ("工作", "lint", "code-review", "verify smart", "fact audit/update", "close-out")


def validate_start(args):
    if args.kind != "adhoc" and getattr(args, "work", None) is not None:
        raise MDFError("--work 仅用于 adhoc", code="unexpected_work")


def objectives():
    return (Path(__file__).resolve().parents[3] / "assets/templates/adhoc-objectives.md").read_text(
        encoding="utf-8"
    )


def prepare(args):
    from mdf_core.foundation.textutil import slugify

    if args.proposal or args.bug or args.version or args.objectives_file:
        raise MDFError("adhoc 不绑定对象或版本，objectives 自动生成", code="invalid_adhoc")
    if not args.name or not args.name.strip():
        raise MDFError("adhoc 需要 Agent 选定的 --name", code="invalid_slug")
    if not args.work or not args.work.strip():
        raise MDFError("adhoc 需要非空 --work 工作描述", code="missing_adhoc_work")
    if (args.roster not in (None, "solo") or args.qa not in (None, 0)
            or args.dev not in (None, 0) or args.reviewers not in (None, 1)):
        raise MDFError("adhoc 的 roster 固定为 0,0,1", code="invalid_adhoc")
    text = objectives()
    require_objectives(text, starting=True)
    return slugify(args.name), text


def require_objectives(text, *, starting=False, finishing=False):
    items = re.findall(r"(?m)^- \[([ x])\] (.+?)\s*$", text)
    if tuple(name for _, name in items) != STEPS:
        raise MDFError("adhoc 必须按固定顺序填写六项步骤", code="invalid_adhoc_objectives")
    checked = [mark == "x" for mark, _ in items]
    if starting and any(checked):
        raise MDFError("adhoc 启动时六项步骤均须未勾选", code="invalid_adhoc_objectives")
    if any(checked[index] and not checked[index - 1] for index in range(1, len(checked))):
        raise MDFError("adhoc 步骤须顺序完成，返工须退勾后续项", code="invalid_adhoc_objectives")
    if finishing and not all(checked):
        raise MDFError("adhoc 尚有未完成步骤", code="adhoc_work_pending")
    return next((step for step, done in zip(STEPS, checked) if not done), None)


def require_identity(data):
    work = data.get("work")
    roster = data["roster"]
    if (not isinstance(work, str) or not work.strip() or data["needs_design"]
            or data.get("proposal") or data.get("bug") or data.get("manual")
            or data["branch"] != f"adhoc/{data['slug']}"
            or tuple(roster[key] for key in ("qa", "dev", "reviewers")) != (0, 0, 1)):
        raise MDFError("adhoc 身份需要工作描述、固定 solo 且不绑定对象或 design", code="invalid_delivery")


def merged_commit(repo, head):
    from mdf_core.lifecycle.delivery_state import git

    merges = git(repo, "rev-list", "--parents", "--merges", "--first-parent", "refs/heads/develop")
    for line in merges.stdout.splitlines():
        fields = line.split()
        if head in fields[2:]:
            return fields[0]
    return None


def command_status(args):
    """从原有材料与 Git 核对进度；detached 时须显式指定已知 slug。"""
    from mdf_core.lifecycle.delivery_state import git, locate, safe
    from mdf_core.foundation.errors import emit
    from mdf_core.workspace.gitutil import (
        branch_details,
        ensure_clean,
        primary_worktree,
        repo_path,
        require_git_root,
    )
    from mdf_core.foundation.textutil import slugify

    repo = repo_path(args.repo)
    require_git_root(repo)
    branch = git(repo, "branch", "--show-current").stdout.strip()
    slug = args.slug
    if slug is None and branch.startswith("adhoc/"):
        slug = branch_details(branch)["slug"]
    if not slug or slugify(slug) != slug:
        raise MDFError("adhoc-status 需要当前 adhoc 或上下文已知的 --slug", code="invalid_slug")
    owner = f"adhoc/{slug}"
    if branch and branch != owner:
        raise MDFError("adhoc-status 必须绑定本次 owner worktree", code="stage_branch")
    root, data = locate(repo, slug, owner=owner)
    try:
        text = safe(repo, root / "objectives.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise MDFError("adhoc objectives 缺失或不可读", code="invalid_adhoc_objectives") from exc
    pending = require_objectives(text)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    merge_commit = merged_commit(repo, head)
    if merge_commit and pending is not None:
        raise MDFError("已合并的 adhoc 账本仍有未完成项，保留现场", code="invalid_delivery")
    if not branch:
        ensure_clean(repo)
        source_exists = not git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{owner}",
                                check=False).returncode
        if pending is not None or source_exists or merge_commit is None:
            raise MDFError("缺少 adhoc 实际收口证据，保留现场", code="adhoc_not_finished")
    emit({"ok": True, "operation": "adhoc-status", "result": {
        "delivery": data, "path": str(root.relative_to(repo)), "head": head,
        "next_step": (pending or "close-out") if branch else None,
        "completed": not branch, "merge_commit": merge_commit,
        "owner_worktree": str(repo), "primary_worktree": str(primary_worktree(repo)),
    }})


def completion(repo, source):
    from mdf_core.lifecycle.delivery_state import locate, require_finish
    from mdf_core.foundation.yamlutil import read_frontmatter

    root, data = locate(repo)
    require_finish(repo, root, data)
    require_objectives((root / "objectives.md").read_text(encoding="utf-8"), finishing=True)
    change = root / "CHANGE.md"
    if not change.is_file():
        raise MDFError("finish 前必须补齐 Change", code="missing_change")
    meta, _ = read_frontmatter(change)
    if (meta.get("change_kind") not in {"adhoc", "fix"} or meta.get("proposals") != []
            or meta.get("source_branch") != source):
        raise MDFError("adhoc 的 Change 必须对应源分支且不引用 PRP", code="invalid_change")
    return data["roster"]
