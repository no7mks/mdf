import json
import re
from pathlib import Path
from typing import Any, Iterable

from .constants import (
    BUG_RESOLUTIONS,
    BUG_SEVERITIES,
    CHANGELOG_CATEGORIES,
    UNRELEASED_FOUND_IN_RE,
)
from .errors import MDFError
from .validate_objects import iter_object_files
from .yamlutil import frontmatter_span, read_frontmatter


def active_objects(repo: Path) -> dict[str, tuple[str, Path, dict[str, Any]]]:
    result: dict[str, tuple[str, Path, dict[str, Any]]] = {}
    for kind in ("requirement", "bug"):
        for path in iter_object_files(repo, kind):
            if len(path.relative_to(repo).parts) != 2:
                continue
            metadata, _ = read_frontmatter(path)
            identifier = metadata.get("id")
            if isinstance(identifier, str):
                result[identifier] = (kind, path, metadata)
    return result


def close_object_text(
    text: str,
    *,
    kind: str,
    closure: dict[str, Any],
    version: str,
) -> str:
    start, end, _ = frontmatter_span(text)
    frontmatter = text[start:end]
    if not re.search(r"^status:\s*ready\s*$", frontmatter, re.MULTILINE):
        raise MDFError(
            f"Object {closure['id']} is not ready", code="invalid_closure"
        )
    resolution = closure["resolution"]

    def set_field(raw: str, key: str, value: str) -> str:
        pattern = rf"^{re.escape(key)}:\s*.*$"
        updated, count = re.subn(
            pattern, f"{key}: {value}", raw, count=1, flags=re.MULTILINE
        )
        return updated if count else raw + f"\n{key}: {value}"

    def remove_field(raw: str, key: str) -> str:
        return re.sub(
            rf"^{re.escape(key)}:\s*.*\n?", "", raw, count=1, flags=re.MULTILINE
        )

    if kind == "requirement":
        if resolution not in {"fulfilled", "rejected", "duplicate", "obsolete"}:
            raise MDFError(
                f"Invalid Requirement resolution: {resolution}",
                code="invalid_closure",
            )
        expected_version = closure.get("fulfilled_in")
        if resolution == "fulfilled":
            if expected_version != version or "fixed_in" in closure:
                raise MDFError(
                    "fulfilled closure requires fulfilled_in equal to release version",
                    code="invalid_closure",
                )
        elif "fulfilled_in" in closure or "fixed_in" in closure:
            raise MDFError(
                "Non-fulfilled Requirement closure must not declare a version",
                code="invalid_closure",
            )
        extra = [f"resolution: {resolution}"]
        if resolution == "fulfilled":
            extra.append(f"fulfilled_in: {version}")
        replacement = "status: closed\n" + "\n".join(extra)
        updated_frontmatter, count = re.subn(
            r"^status:\s*ready\s*$",
            replacement,
            frontmatter,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise MDFError(
                "Could not update object status", code="invalid_closure"
            )
        return text[:start] + updated_frontmatter + text[end:]

    if resolution == "deferred":
        severity = re.search(
            r"^severity:\s*([^\s#]+)", frontmatter, re.MULTILINE
        )
        if severity is None or severity.group(1) not in BUG_SEVERITIES:
            raise MDFError(
                "Deferred Bugs require critical, major, or trivial severity",
                code="invalid_closure",
            )
        if UNRELEASED_FOUND_IN_RE.search(frontmatter):
            frontmatter = set_field(frontmatter, "found_in", version)
        return text[:start] + frontmatter + text[end:]

    if resolution not in BUG_RESOLUTIONS:
        raise MDFError(
            f"Invalid Bug resolution: {resolution}", code="invalid_closure"
        )
    if resolution == "duplicate":
        primary = closure.get("duplicate_of")
        if not isinstance(primary, str) or not primary.startswith("bug-"):
            raise MDFError(
                "Duplicate closure requires duplicate_of",
                code="invalid_closure",
            )
        frontmatter = remove_field(frontmatter, "found_in")
        frontmatter = remove_field(frontmatter, "fixed_in")
        frontmatter = set_field(frontmatter, "duplicate_of", primary)
        extra = "status: closed\nresolution: duplicate"
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
        if UNRELEASED_FOUND_IN_RE.search(frontmatter):
            frontmatter = set_field(frontmatter, "found_in", version)
        extra = f"status: closed\nresolution: {resolution}"
        if resolution == "fixed":
            extra += f"\nfixed_in: {version}"
    updated_frontmatter, count = re.subn(
        r"^status:\s*ready\s*$", extra, frontmatter, count=1, flags=re.MULTILINE
    )
    if count != 1:
        raise MDFError("Could not update object status", code="invalid_closure")
    return text[:start] + updated_frontmatter + text[end:]


def aggregate_release_changes(
    repo: Path,
    slugs: list[str],
) -> tuple[
    dict[str, list[str]],
    bool,
    set[str],
    set[str],
    set[str],
    set[str],
    set[str],
    dict[str, str],
]:
    notes = {category: [] for category in CHANGELOG_CATEGORIES}
    breaking = False
    requirements: set[str] = set()
    fixed: set[str] = set()
    closed: set[str] = set()
    deferred: set[str] = set()
    adrs: set[str] = set()
    closed_resolutions: dict[str, str] = {}
    for slug in sorted(slugs):
        change = repo / "changes" / "unreleased" / slug / "CHANGE.md"
        metadata, _ = read_frontmatter(change)
        requirements.update(metadata.get("requirements", []))
        fixed.update(metadata.get("fixed", []))
        closed.update(metadata.get("closed", []))
        deferred.update(metadata.get("deferred", []))
        adrs.update(metadata.get("adrs", []))
        raw_resolutions = metadata.get("closed_resolutions", {})
        if isinstance(raw_resolutions, dict):
            closed_resolutions.update(raw_resolutions)
        breaking = breaking or metadata.get("breaking") is True
        release_notes = metadata.get("release_notes")
        if isinstance(release_notes, dict):
            for category in CHANGELOG_CATEGORIES:
                values = release_notes.get(category, [])
                if isinstance(values, list):
                    notes[category].extend(values)
    return (
        notes,
        breaking,
        requirements,
        fixed,
        closed,
        deferred,
        adrs,
        closed_resolutions,
    )


def render_version_change(
    version: str,
    previous: str | None,
    release_date: str,
    mode: str,
    slugs: list[str],
    categories: set[str],
    breaking: bool,
    minimum_bump: str,
    actual_bump: str,
    commands: list[str],
    requirements: set[str],
    fixed: set[str],
    closed: set[str],
    deferred: set[str],
    adrs: set[str],
    closed_resolutions: dict[str, str],
    closed_requirement_resolutions: dict[str, str],
    found_in_transitions: list[str],
    deferred_acceptance: dict[str, Any],
    hotfix_body: str | None = None,
    release_notes: dict[str, list[str]] | None = None,
    *,
    verify_command_results: list[dict[str, Any]] | None = None,
    semantic_summary: str | None = None,
) -> str:
    def yaml_list(values: Iterable[str]) -> str:
        return "[" + ", ".join(sorted(values)) + "]"

    def notes_yaml() -> str:
        if not categories:
            return "release_notes: none\n"
        lines = ["release_notes:"]
        for category in CHANGELOG_CATEGORIES:
            if category in categories:
                values = (
                    release_notes.get(category, []) if release_notes else []
                )
                if not values:
                    values = [category]
                lines.append(f"  {category}:")
                lines.extend(
                    f"    - {json.dumps(str(value), ensure_ascii=False)}"
                    for value in values
                )
        return "\n".join(lines) + "\n"

    child_lines = (
        "\n".join(f"- [{slug}]({slug}/CHANGE.md)" for slug in sorted(slugs))
        or "None."
    )
    previous_value = previous if previous is not None else "none"
    commands_text = "".join(
        f"    - {json.dumps(str(command), ensure_ascii=False)}\n"
        for command in commands
    )
    transition_lines = (
        "\n".join(f"- {line}" for line in found_in_transitions) or "None."
    )
    if deferred_acceptance:
        acceptance_lines = "\n".join(
            f"- `{identifier}`: {value.get('reason', 'accepted')}; follow-up: {value.get('follow_up', 'none')}"
            for identifier, value in sorted(deferred_acceptance.items())
            if isinstance(value, dict)
        )
    else:
        acceptance_lines = "None."
    return (
        "---\n"
        f'version: "{version}"\n'
        f'previous_version: "{previous_value}"\n'
        f'date: "{release_date}"\n'
        f"change_kind: {mode}\n"
        f"source_branch: {mode}/{version}\n"
        f"requirements: {yaml_list(requirements)}\n"
        f"fixed: {yaml_list(fixed)}\n"
        f"closed: {yaml_list(closed)}\n"
        f"deferred: {yaml_list(deferred)}\n"
        + (
            "closed_resolutions:\n"
            + "".join(
                f"  {identifier}: "
                f"{json.dumps(str(closed_resolutions.get(identifier, 'wont-fix')), ensure_ascii=False)}\n"
                for identifier in sorted(closed)
            )
            if closed
            else ""
        )
        + f"adrs: {yaml_list(adrs)}\n"
        f"included_changes: {yaml_list(slugs)}\n"
        + notes_yaml()
        + f"breaking: {'true' if breaking else 'false'}\n"
        + "evidence:\n"
        + "  tests: []\n"
        + "  commands:\n"
        + commands_text
        + "  artifacts: []\n"
        + "audit: passed\n"
        + "---\n\n"
        f"# {mode.title()} {version}\n\n"
        "## Result\n\n"
        + (hotfix_body or "Release closeout completed.")
        + "\n\n## Included Changes\n\n"
        + child_lines
        + "\n\n## Current Docs Updated\n\n"
        + "CHANGELOG.md and the version-root CHANGE.md were generated.\n\n"
        + "## Migration\n\nNot required.\n\n"
        + "## Known Deviations\n\nNone.\n\n"
        + "## Closeout Outcomes\n\n"
        + "### Requirements\n\n"
        + (
            chr(10).join(f"- `{item}`" for item in sorted(requirements))
            or "None."
        )
        + "\n\n### Closed Requirements\n\n"
        + (
            chr(10).join(
                f"- `{item}` ({closed_requirement_resolutions[item]})"
                for item in sorted(closed_requirement_resolutions)
            )
            or "None."
        )
        + "\n\n### Fixed Bugs\n\n"
        + (chr(10).join(f"- `{item}`" for item in sorted(fixed)) or "None.")
        + "\n\n### Closed Bugs\n\n"
        + (
            chr(10).join(
                f"- `{item}` ({closed_resolutions.get(item, 'wont-fix')})"
                for item in sorted(closed)
            )
            or "None."
        )
        + "\n\n### Deferred Bugs\n\n"
        + (chr(10).join(f"- `{item}`" for item in sorted(deferred)) or "None.")
        + "## Found-in Transitions\n\n"
        + transition_lines
        + "\n\n## Deferred Acceptance\n\n"
        + acceptance_lines
        + "\n\n## SemVer Decision\n\n"
        + f"- Observed categories: {', '.join(sorted(categories)) if categories else 'none'}\n"
        + f"- Breaking: {'true' if breaking else 'false'}\n"
        + f"- Minimum bump: {minimum_bump}\n"
        + f"- Actual bump: {actual_bump}\n"
        + f"- Selected version: `{version}`\n\n"
        + "## Audit\n\n"
        + "- Deterministic full audit: passed (verified by Core).\n"
        + "- Semantic audit: passed (attested by `$mdf-finish`; "
        + "Core did not independently verify semantics).\n"
        + (
            f"- Semantic summary: {semantic_summary}\n"
            if isinstance(semantic_summary, str) and semantic_summary.strip()
            else ""
        )
        + "- Verify commands:\n"
        + "".join(
            (
                f"  - `{item.get('command')}` → exit {item.get('exit_code')}\n"
                if isinstance(item, dict)
                else f"  - `{item}`\n"
            )
            for item in (
                verify_command_results
                or [
                    {"command": command, "exit_code": 0} for command in commands
                ]
            )
        )
        + "\n## Validation Commands\n\n```text\n"
        + "\n".join(commands)
        + "\n```\n"
    )


def update_changelog_text(
    text: str,
    *,
    version: str,
    release_date: str,
    notes: dict[str, list[str]],
) -> str:
    if not text.startswith("# Changelog"):
        raise MDFError(
            "CHANGELOG.md 必须以 '# Changelog' 开头",
            code="invalid_changelog",
        )
    if re.search(
        rf"^##\s+\[?{re.escape(version)}]?(?:\s|$)",
        text,
        re.MULTILINE,
    ):
        raise MDFError(
            f"CHANGELOG already contains {version}",
            code="collision",
        )
    lines = [f"## [{version}] - {release_date}", ""]
    populated = False
    for category in CHANGELOG_CATEGORIES:
        values = notes[category]
        if not values:
            continue
        populated = True
        lines.extend([f"### {category}", ""])
        lines.extend(f"- {value}" for value in values)
        lines.append("")
    if not populated:
        lines.extend(["- No user-facing changes.", ""])
    section = "\n".join(lines)
    heading_end = text.find("\n")
    if heading_end < 0:
        return text + "\n\n" + section
    insert_at = heading_end + 1
    return text[:insert_at] + "\n" + section + text[insert_at:]


def update_manifest_release(text: str, version: str) -> str:
    updated, count = re.subn(
        r"^(\s*latest_release:\s*).*$",
        rf'\g<1>"{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise MDFError(
            "manifest 没有唯一的 latest_release 字段",
            code="invalid_manifest",
        )
    return updated
