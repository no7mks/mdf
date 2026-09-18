"""项目具名验证项与 suite；失败标准由项目命令负责。"""
import json
import re

from .errors import MDFError

KINDS = {"unit", "property", "integration", "e2e", "lint", "typecheck", "build", "custom"}
NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
GLOBAL_SUITES = ("quick", "full")
ITEM_KEYS = {"id", "kind", "command"}


def _name(value):
    return isinstance(value, str) and bool(NAME_RE.fullmatch(value))


class Verification:
    """manifest.verification 的已校验视图：items 为验证项，suites 为 name -> ids（未分层时为 None）。"""

    def __init__(self, items, suites):
        self.items = items
        self.suites = suites

    @property
    def layered(self):
        return self.suites is not None

    def delivery_suites(self):
        return set(self.suites or {}) - set(GLOBAL_SUITES)

    def select(self, wanted):
        if not self.layered or "full" in wanted:
            return list(self.items)
        ids = set()
        for name in wanted:
            ids.update(self.suites.get(name, []))
        return [item for item in self.items if item["id"] in ids]

    def required(self, kind, declared=None):
        if not self.layered:
            return ["quick", "full"]
        if kind in {"release", "hotfix"}:
            return ["full"]
        if kind not in {"feature", "bugfix"}:
            raise MDFError("验证 suite 需要 Gitflow 交付分支", code="unsupported_branch")
        names = list(declared or [])
        if not names:
            raise MDFError("分层后必须声明本交付 suite", code="missing_delivery_suite")
        unknown = [name for name in names if name not in self.delivery_suites()]
        if unknown:
            code = "unknown_suite" if kind == "bugfix" else "missing_delivery_suite"
            message = (
                "bugfix 只能关联已有交付 suite，新建须用户确认后写入 manifest"
                if kind == "bugfix"
                else "本交付 suite 未在 manifest verification.suites 中声明"
            )
            raise MDFError(message, code=code, details={"unknown": unknown})
        return ["quick", *names]

    def recorded(self, record):
        raw = record.get("suites")
        if raw is None and not self.layered:
            return ["quick", "full"]
        if not isinstance(raw, list) or not raw or any(not isinstance(name, str) for name in raw):
            return []
        return raw


def parse_suite_names(raw):
    if not isinstance(raw, list) or not raw:
        raise MDFError("交付 suite 必须为非空名称列表", code="invalid_delivery_suite")
    seen = []
    for name in raw:
        if not _name(name) or name in GLOBAL_SUITES or name in seen:
            raise MDFError(
                "交付 suite 名称无效、重复或占用 quick/full",
                code="invalid_delivery_suite",
            )
        seen.append(name)
    return seen


def suites_cover(recorded, required):
    return set(recorded) >= set(required)


def validate_items(items):
    if not isinstance(items, list) or not items:
        raise MDFError("verification.commands 必须为非空具名验证项列表", code="invalid_verification")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != ITEM_KEYS:
            raise MDFError("验证项只接受 id、kind、command", code="invalid_verification")
        identifier = item["id"]
        if (not _name(identifier) or identifier in seen or item["kind"] not in KINDS
                or not isinstance(item["command"], str) or not item["command"].strip()):
            raise MDFError("验证项 ID、类别或命令无效", code="invalid_verification")
        seen.add(identifier)
    return items


def validate_suites(suites, items):
    if suites is None:
        return None
    if not isinstance(suites, dict) or "quick" not in suites:
        raise MDFError("verification.suites 必须是含 quick 的映射", code="invalid_verification")
    if "full" in suites:
        raise MDFError("full 隐含为全部验证项，不得在 verification.suites 声明",
                       code="invalid_verification")
    ids = {item["id"] for item in items}
    for name, members in suites.items():
        if not _name(name):
            raise MDFError("suite 名必须为 kebab-case", code="invalid_verification")
        if (not isinstance(members, list) or not members
                or len(members) != len(set(members))
                or any(member not in ids for member in members)):
            raise MDFError(f"suite {name} 必须是非空、不重复且存在的验证项 id 列表",
                           code="invalid_verification")
    return suites


def manifest_verification(manifest):
    verification = manifest.get("verification")
    if not isinstance(verification, dict):
        raise MDFError("verification.commands 必须为非空具名验证项列表", code="invalid_verification")
    items = validate_items(verification.get("commands"))
    return Verification(items, validate_suites(verification.get("suites"), items))


def manifest_items(manifest):
    return manifest_verification(manifest).items


def parse_items(raw):
    try:
        return validate_items([json.loads(value) for value in raw])
    except (ValueError, TypeError) as exc:
        raise MDFError("--verification-item 必须是含 id/kind/command 的 JSON",
                       code="invalid_verification") from exc
