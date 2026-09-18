"""项目具名验证项；失败标准由项目命令负责。"""
import json
import re

from .errors import MDFError

KINDS = {"unit", "property", "integration", "e2e", "lint", "typecheck", "build", "custom"}
NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
GLOBAL_COLLECTIONS = ("quick", "full")
BASE_KEYS = {"id", "kind", "command"}
LAYERED_KEYS = {"id", "kind", "command", "collections"}


def _name(value):
    return isinstance(value, str) and bool(NAME_RE.fullmatch(value))


def is_layered(items):
    return any("collections" in item for item in items)


def named_suites(items):
    names = set()
    for item in items:
        for name in item.get("collections", []):
            if name not in GLOBAL_COLLECTIONS:
                names.add(name)
    return names


def parse_suite_names(raw):
    if not isinstance(raw, list) or not raw:
        raise MDFError("交付 suite 必须为非空名称列表", code="invalid_delivery_suite")
    seen = []
    for name in raw:
        if not _name(name) or name in GLOBAL_COLLECTIONS or name in seen:
            raise MDFError(
                "交付 suite 名称无效、重复或占用 quick/full",
                code="invalid_delivery_suite",
            )
        seen.append(name)
    return seen


def select_items(items, collections):
    if not is_layered(items):
        return list(items)
    wanted = set(collections)
    selected = []
    seen = set()
    for item in items:
        identifier = item["id"]
        if wanted & set(item["collections"]) and identifier not in seen:
            selected.append(item)
            seen.add(identifier)
    return selected


def required_collections(kind, items, suites=None):
    if not is_layered(items):
        return ["quick", "full"]
    if kind in {"release", "hotfix"}:
        return ["full"]
    if kind not in {"feature", "bugfix"}:
        raise MDFError("验证集合需要 Gitflow 交付分支", code="unsupported_branch")
    names = list(suites or [])
    if not names:
        raise MDFError("分层后必须声明本交付 suite", code="missing_delivery_suite")
    unknown = [name for name in names if name not in named_suites(items)]
    if unknown:
        code = "unknown_suite" if kind == "bugfix" else "missing_delivery_suite"
        message = (
            "bugfix 只能关联已有交付 suite，新建须用户确认后写入 manifest"
            if kind == "bugfix"
            else "本交付 suite 在验证项中没有可执行命令"
        )
        raise MDFError(message, code=code, details={"unknown": unknown})
    return ["quick", *names]


def recorded_collections(record, items):
    raw = record.get("collections")
    if raw is None and not is_layered(items):
        return ["quick", "full"]
    if not isinstance(raw, list) or not raw or any(not isinstance(name, str) for name in raw):
        return []
    return raw


def collections_cover(recorded, required):
    return set(recorded) >= set(required)


def validate_items(items):
    if not isinstance(items, list) or not items:
        raise MDFError("verification.commands 必须为非空具名验证项列表", code="invalid_verification")
    layered = any(isinstance(item, dict) and "collections" in item for item in items)
    seen = set()
    has_quick = False
    has_full = False
    for item in items:
        expected = LAYERED_KEYS if layered else BASE_KEYS
        if not isinstance(item, dict) or set(item) != expected:
            raise MDFError(
                "验证项只接受 id、kind、command；分层后每项还必须有 collections",
                code="invalid_verification",
            )
        identifier = item["id"]
        if (not _name(identifier) or identifier in seen or item["kind"] not in KINDS
                or not isinstance(item["command"], str) or not item["command"].strip()):
            raise MDFError("验证项 ID、类别或命令无效", code="invalid_verification")
        if layered:
            names = item["collections"]
            if (not isinstance(names, list) or not names
                    or len(names) != len(set(names))
                    or any(not _name(name) for name in names)):
                raise MDFError("collections 必须为非空唯一 kebab-case 名称列表",
                               code="invalid_verification")
            if "quick" in names and "full" not in names:
                raise MDFError("声明 quick 的验证项必须同时声明 full",
                               code="invalid_verification")
            has_quick = has_quick or "quick" in names
            has_full = has_full or "full" in names
        seen.add(identifier)
    if layered and (not has_quick or not has_full):
        raise MDFError("分层后 quick 与 full 均不得为空", code="invalid_verification")
    return items


def manifest_items(manifest):
    verification = manifest.get("verification")
    return validate_items(verification.get("commands") if isinstance(verification, dict) else None)


def parse_items(raw):
    try:
        return validate_items([json.loads(value) for value in raw])
    except (ValueError, TypeError) as exc:
        raise MDFError("--verification-item 必须是含 id/kind/command 的 JSON",
                       code="invalid_verification") from exc
