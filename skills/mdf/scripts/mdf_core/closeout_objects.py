import re
from pathlib import Path
from typing import Any

from .constants import (
    BUG_RESOLUTIONS,
    BUG_SEVERITIES,
    is_unreleased_sentinel,
)
from .errors import MDFError
from .validate_objects import iter_object_files
from .yamlutil import frontmatter_span, parse_yaml


def active_objects(repo: Path) -> dict[str, tuple[str, Path, dict[str, Any]]]:
    result: dict[str, tuple[str, Path, dict[str, Any]]] = {}
    for kind in ("proposal", "bug"):
        for path in iter_object_files(repo, kind):
            if len(path.relative_to(repo).parts) != 2:
                continue
            text = path.read_text(encoding="utf-8")
            start, end, _ = frontmatter_span(text)
            metadata = parse_yaml(text[start:end])
            identifier = metadata.get("id")
            if isinstance(identifier, str):
                result[identifier] = (kind, path, metadata)
    return result


def _set_field(frontmatter: str, key: str, value: str) -> str:
    pattern = rf"^{re.escape(key)}:\s*.*$"
    updated, count = re.subn(
        pattern,
        f"{key}: {value}",
        frontmatter,
        count=1,
        flags=re.MULTILINE,
    )
    return updated if count else frontmatter + f"\n{key}: {value}"


def _remove_field(frontmatter: str, key: str) -> str:
    return re.sub(
        rf"^{re.escape(key)}:\s*.*\n?",
        "",
        frontmatter,
        count=1,
        flags=re.MULTILINE,
    )


def _require_ready(metadata: dict[str, Any], identifier: str) -> None:
    if metadata.get("status") != "ready":
        raise MDFError(
            f"Object {identifier} is not ready", code="invalid_closure"
        )


def close_object_text(
    text: str,
    *,
    kind: str,
    closure: dict[str, Any],
    version: str,
) -> str:
    """Close one object from parsed YAML state and normalize changed fields."""
    start, end, _ = frontmatter_span(text)
    frontmatter = text[start:end]
    metadata = parse_yaml(frontmatter)
    identifier = closure.get("id")
    _require_ready(metadata, str(identifier))
    resolution = closure["resolution"]

    if kind == "proposal":
        allowed = {"fulfilled", "rejected", "duplicate", "obsolete"}
        if resolution not in allowed:
            raise MDFError(
                f"Invalid Proposal resolution: {resolution}",
                code="invalid_closure",
            )
        expected_version = closure.get("fulfilled_in")
        if resolution == "fulfilled":
            if expected_version != version or "fixed_in" in closure:
                raise MDFError(
                    "fulfilled closure requires fulfilled_in equal to release "
                    "version",
                    code="invalid_closure",
                )
        elif "fulfilled_in" in closure or "fixed_in" in closure:
            raise MDFError(
                "Non-fulfilled Proposal closure must not declare a version",
                code="invalid_closure",
            )
        frontmatter = _set_field(frontmatter, "status", "closed")
        frontmatter = _set_field(frontmatter, "resolution", resolution)
        if resolution == "fulfilled":
            frontmatter = _set_field(frontmatter, "fulfilled_in", version)
        return text[:start] + frontmatter + text[end:]

    if resolution == "deferred":
        severity = metadata.get("severity")
        if severity not in BUG_SEVERITIES:
            raise MDFError(
                "Deferred Bugs require critical, major, or trivial severity",
                code="invalid_closure",
            )
        if is_unreleased_sentinel(metadata.get("found_in")):
            frontmatter = _set_field(frontmatter, "found_in", version)
        return text[:start] + frontmatter + text[end:]

    if resolution not in BUG_RESOLUTIONS:
        raise MDFError(
            f"Invalid Bug resolution: {resolution}",
            code="invalid_closure",
        )
    if resolution == "duplicate":
        primary = closure.get("duplicate_of")
        if not isinstance(primary, str) or not primary.startswith("bug-"):
            raise MDFError(
                "Duplicate closure requires duplicate_of",
                code="invalid_closure",
            )
        frontmatter = _remove_field(frontmatter, "found_in")
        frontmatter = _remove_field(frontmatter, "fixed_in")
        frontmatter = _set_field(frontmatter, "duplicate_of", primary)
    else:
        if resolution == "fixed":
            if closure.get("fixed_in") != version or "fulfilled_in" in closure:
                raise MDFError(
                    "fixed closure requires fixed_in equal to release version",
                    code="invalid_closure",
                )
        elif "fixed_in" in closure or "fulfilled_in" in closure:
            raise MDFError(
                "Non-fixed Bug closure must not declare a version",
                code="invalid_closure",
            )
        if is_unreleased_sentinel(metadata.get("found_in")):
            frontmatter = _set_field(frontmatter, "found_in", version)
        if resolution == "fixed":
            frontmatter = _set_field(frontmatter, "fixed_in", version)
    frontmatter = _set_field(frontmatter, "status", "closed")
    frontmatter = _set_field(frontmatter, "resolution", resolution)
    return text[:start] + frontmatter + text[end:]
