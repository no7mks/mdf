"""Adhoc 的固定 objectives 与无 PRP 收口。"""
import re
from pathlib import Path

from .errors import MDFError

STEPS = ("工作", "code-review", "verify smart", "fact audit/update", "close-out")


def objectives():
    return (Path(__file__).resolve().parents[2] / "assets/templates/adhoc-objectives.md").read_text(
        encoding="utf-8"
    )


def prepare(args):
    from .textutil import slugify

    if args.proposal or args.bug or args.version or args.objectives_file:
        raise MDFError("adhoc 不绑定对象或版本，objectives 自动生成", code="invalid_adhoc")
    if not args.name or not args.name.strip():
        raise MDFError("adhoc 需要 Agent 选定的 --name", code="invalid_slug")
    if (args.roster not in (None, "solo") or args.qa not in (None, 0)
            or args.dev not in (None, 0) or args.reviewers not in (None, 1)):
        raise MDFError("adhoc 的 roster 固定为 0,0,1", code="invalid_adhoc")
    text = objectives()
    require_objectives(text, starting=True)
    return slugify(args.name), text


def require_objectives(text, *, starting=False, finishing=False):
    items = re.findall(r"(?m)^- \[([ x])\] (.+?)\s*$", text)
    if tuple(name for _, name in items) != STEPS:
        raise MDFError("adhoc 必须按固定顺序填写五项步骤", code="invalid_adhoc_objectives")
    checked = [mark == "x" for mark, _ in items]
    if starting and any(checked):
        raise MDFError("adhoc 启动时五项步骤均须未勾选", code="invalid_adhoc_objectives")
    if finishing and not all(checked):
        raise MDFError("adhoc 尚有未完成步骤", code="adhoc_work_pending")


def completion(repo, source):
    from .delivery_state import locate, require_finish
    from .yamlutil import read_frontmatter

    root, data = locate(repo)
    require_finish(repo, root, data)
    require_objectives((root / "objectives.md").read_text(encoding="utf-8"), finishing=True)
    change = root / "CHANGE.md"
    if not change.is_file():
        raise MDFError("finish 前必须补齐 Change", code="missing_change")
    meta, _ = read_frontmatter(change)
    if (meta.get("change_kind") != "adhoc" or meta.get("proposals") != []
            or meta.get("source_branch") != source):
        raise MDFError("adhoc 的 Change 必须对应源分支且不引用 PRP", code="invalid_change")
    return data["roster"]
