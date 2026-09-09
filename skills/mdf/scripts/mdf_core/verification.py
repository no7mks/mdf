"""项目具名验证项；失败标准由项目命令负责。"""
import json
import re

from .errors import MDFError

KINDS = {"unit", "property", "integration", "e2e", "lint", "typecheck", "build", "custom"}


def validate_items(items):
    if not isinstance(items, list) or not items:
        raise MDFError("verification.commands 必须为非空具名验证项列表", code="invalid_verification")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "kind", "command"}:
            raise MDFError("验证项只接受 id、kind、command", code="invalid_verification")
        identifier = item["id"]
        if (not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identifier)
                or identifier in seen or not isinstance(item["kind"], str) or item["kind"] not in KINDS
                or not isinstance(item["command"], str) or not item["command"].strip()):
            raise MDFError("验证项 ID、类别或命令无效", code="invalid_verification")
        seen.add(identifier)
    return items


def manifest_items(manifest):
    verification = manifest.get("verification")
    return validate_items(verification.get("commands") if isinstance(verification, dict) else None)


def parse_items(raw):
    try:
        return validate_items([json.loads(value) for value in raw])
    except (ValueError, TypeError) as exc:
        raise MDFError("--verification-item 必须是含 id/kind/command 的 JSON", code="invalid_verification") from exc
