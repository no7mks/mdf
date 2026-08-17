import re
from pathlib import Path
from typing import Any, Iterable

from .constants import (
    BUG_RESOLUTIONS,
    BUG_SEVERITIES,
    EPOCH_RE,
    MARKER_RE,
    OBJECT_FILE_RE,
    contains_unreleased_sentinel,
    is_unreleased_sentinel,
)
from .errors import Finding, MDFError, add_finding
from .paths import path_stays_in_repo, relative
from .textutil import stable_semver
from .yamlutil import read_frontmatter


def iter_object_files(repo: Path, kind: str) -> Iterable[Path]:
    root = repo / ("proposals" if kind == "proposal" else "bugs")
    if (
        not root.is_dir()
        or root.is_symlink()
        or not path_stays_in_repo(repo, root)
    ):
        return []
    # Collect every Markdown candidate so a misplaced prp-*/bug-* file is
    # validated (and rejected) instead of being silently ignored.
    return sorted(
        path
        for path in root.rglob("*.md")
        if path.is_file()
        and not path.is_symlink()
        and path_stays_in_repo(repo, path)
    )


def required_sections(
    body: str, headings: Iterable[str], rel: str, findings: list[Finding]
) -> None:
    for heading in headings:
        if not re.search(
            rf"^##+\s+{re.escape(heading)}\s*$", body, re.MULTILINE
        ):
            add_finding(
                findings,
                "document.section",
                f"Missing required section: {heading}",
                rel,
            )


def validate_object(
    repo: Path, path: Path, expected_type: str, findings: list[Finding]
) -> None:
    rel = relative(repo, path)
    filename = OBJECT_FILE_RE.fullmatch(path.name)
    expected_prefix = "prp" if expected_type == "proposal" else "bug"
    if not filename or filename.group(1) != expected_prefix:
        add_finding(
            findings,
            "object.filename",
            f"Invalid {expected_type} filename",
            rel,
        )
        return
    expected_id = f"{filename.group(1)}-{filename.group(2)}"
    try:
        metadata, body = read_frontmatter(path)
    except (OSError, MDFError) as exc:
        add_finding(findings, "object.frontmatter", str(exc), rel)
        return
    if metadata.get("id") != expected_id:
        add_finding(findings, "object.id", f"id must equal {expected_id}", rel)
    if metadata.get("type") != expected_type:
        add_finding(
            findings, "object.type", f"type must equal {expected_type}", rel
        )
    status = metadata.get("status")
    if status not in {"draft", "ready", "closed"}:
        add_finding(
            findings,
            "object.status",
            "status must be draft, ready, or closed",
            rel,
        )

    if expected_type == "proposal":
        related = metadata.get("related")
        if not isinstance(related, list):
            add_finding(
                findings,
                "object.related",
                "Proposal related must be a list of dependency IDs",
                rel,
            )
        elif len(related) != len(set(map(str, related))):
            add_finding(
                findings,
                "object.related_duplicate",
                "Proposal dependencies must not contain duplicate IDs",
                rel,
            )
    elif "related" in metadata:
        add_finding(
            findings,
            "bug.related_forbidden",
            "Bug 不得声明 Proposal related；请使用 duplicate_of",
            rel,
        )

    if MARKER_RE.search(body):
        add_finding(
            findings,
            "object.marker",
            "Object contains an unresolved template marker",
            rel,
        )
    required_headings = (
        ("Problem", "Desired Outcome", "Scope", "Acceptance Criteria")
        if expected_type == "proposal"
        else (
            "Observed Behavior",
            "Expected Behavior",
            "Reproduction",
            "Impact",
            "Regression Evidence Required",
        )
    )
    for heading in required_headings:
        match = re.search(
            rf"^##+\s+{re.escape(heading)}\s*$", body, re.MULTILINE
        )
        if not match:
            add_finding(
                findings,
                "object.section",
                f"Missing required section: {heading}",
                rel,
            )
            continue
        next_heading = re.search(
            r"^#{1,2}\s+\S.*$", body[match.end() :], re.MULTILINE
        )
        section_end = (
            match.end() + next_heading.start() if next_heading else len(body)
        )
        if not body[match.end() : section_end].strip():
            add_finding(
                findings,
                "object.section_empty",
                f"Required section is empty: {heading}",
                rel,
            )
    if expected_type == "proposal":
        scope_match = re.search(r"^##+\s+Scope\s*$", body, re.MULTILINE)
        if scope_match:
            next_heading = re.search(
                r"^#{1,2}\s+\S.*$", body[scope_match.end() :], re.MULTILINE
            )
            scope_end = (
                scope_match.end() + next_heading.start()
                if next_heading
                else len(body)
            )
            scope_body = body[scope_match.end() : scope_end]
            for subsection in ("In", "Out"):
                subsection_match = re.search(
                    rf"^###+\s+{subsection}\s*$", scope_body, re.MULTILINE
                )
                if not subsection_match:
                    add_finding(
                        findings,
                        "proposal.scope",
                        f"Scope requires a {subsection} subsection",
                        rel,
                    )
                    continue
                next_subsection = re.search(
                    r"^###+\s+\S.*$",
                    scope_body[subsection_match.end() :],
                    re.MULTILINE,
                )
                subsection_end = (
                    subsection_match.end() + next_subsection.start()
                    if next_subsection
                    else len(scope_body)
                )
                if not scope_body[
                    subsection_match.end() : subsection_end
                ].strip():
                    add_finding(
                        findings,
                        "proposal.scope_empty",
                        f"Scope {subsection} subsection is empty",
                        rel,
                    )

    resolution = metadata.get("resolution")
    if status == "closed" and not isinstance(resolution, str):
        add_finding(
            findings,
            "object.resolution",
            "Closed objects require resolution",
            rel,
        )
    if status != "closed" and resolution is not None:
        add_finding(
            findings,
            "object.early_resolution",
            "Only closed objects may declare resolution",
            rel,
        )

    rel_parts = Path(rel).parts
    expected_root = "proposals" if expected_type == "proposal" else "bugs"
    if len(rel_parts) == 2 and rel_parts[0] == expected_root:
        pass
    elif (
        len(rel_parts) == 4
        and rel_parts[0] == expected_root
        and rel_parts[1] == "archive"
    ):
        if not EPOCH_RE.fullmatch(rel_parts[2]):
            add_finding(
                findings,
                "archive.path",
                "Archive slice must be MAJOR.MINOR",
                rel,
            )
        if status != "closed":
            add_finding(
                findings,
                "archive.status",
                "Only closed objects may be archived",
                rel,
            )
    else:
        add_finding(
            findings,
            "object.path",
            f"{expected_type} must be directly active or in "
            "archive/MAJOR.MINOR",
            rel,
        )

    if expected_type == "proposal":
        allowed = {"fulfilled", "rejected", "duplicate", "obsolete"}
        if resolution is not None and resolution not in allowed:
            add_finding(
                findings,
                "proposal.resolution",
                f"Unsupported proposal resolution: {resolution}",
                rel,
            )
        fulfilled_in = metadata.get("fulfilled_in")
        if resolution == "fulfilled" and stable_semver(fulfilled_in) is None:
            add_finding(
                findings,
                "proposal.fulfilled_in",
                "A fulfilled proposal needs a stable SemVer fulfilled_in",
                rel,
            )
        if fulfilled_in is not None and stable_semver(fulfilled_in) is None:
            add_finding(
                findings,
                "proposal.version",
                "fulfilled_in must be a stable SemVer",
                rel,
            )
        if resolution != "fulfilled" and fulfilled_in is not None:
            add_finding(
                findings,
                "proposal.fulfilled_in",
                "fulfilled_in is allowed only with resolution fulfilled",
                rel,
            )
    else:
        if resolution is not None and resolution not in BUG_RESOLUTIONS:
            add_finding(
                findings,
                "bug.resolution",
                f"Unsupported bug resolution: {resolution}",
                rel,
            )
        severity = metadata.get("severity")
        if severity is not None and severity not in BUG_SEVERITIES:
            add_finding(
                findings,
                "bug.severity",
                "severity 必须是 critical、major 或 trivial",
                rel,
            )
        if status in {"draft", "ready"} and severity not in BUG_SEVERITIES:
            add_finding(
                findings,
                "bug.severity_required",
                "非 duplicate 的 active Bug 必须有 severity",
                rel,
            )
        duplicate_of = metadata.get("duplicate_of")
        if resolution == "duplicate":
            if status != "closed":
                add_finding(
                    findings,
                    "bug.duplicate_status",
                    "A duplicate Bug must be closed",
                    rel,
                )
            if not isinstance(duplicate_of, str) or not duplicate_of.startswith(
                "bug-"
            ):
                add_finding(
                    findings,
                    "bug.duplicate_of",
                    "duplicate Bug 需要 duplicate_of: bug-...",
                    rel,
                )
            for key in ("found_in", "fixed_in"):
                if key in metadata:
                    add_finding(
                        findings,
                        "bug.duplicate_version",
                        "duplicate Bug 不使用 found_in 或 fixed_in",
                        rel,
                    )
        else:
            if duplicate_of is not None:
                add_finding(
                    findings,
                    "bug.duplicate_of",
                    "duplicate_of 仅允许用于 resolution: duplicate",
                    rel,
                )
            found_in = metadata.get("found_in")
            if (
                not is_unreleased_sentinel(found_in)
                and stable_semver(found_in) is None
            ):
                add_finding(
                    findings,
                    "bug.found_in",
                    "found_in 必须是稳定 SemVer 或 unreleased",
                    rel,
                )
            if status == "closed" and is_unreleased_sentinel(found_in):
                add_finding(
                    findings,
                    "bug.closed_unreleased",
                    "closed Bug 必须关联稳定 found_in 版本",
                    rel,
                )
            fixed_in = metadata.get("fixed_in")
            if resolution == "fixed" and stable_semver(fixed_in) is None:
                add_finding(
                    findings,
                    "bug.fixed_in",
                    "A fixed Bug needs a stable SemVer fixed_in",
                    rel,
                )
            if fixed_in is not None and stable_semver(fixed_in) is None:
                add_finding(
                    findings,
                    "bug.version",
                    "fixed_in must be a stable SemVer",
                    rel,
                )
            if resolution != "fixed" and fixed_in is not None:
                add_finding(
                    findings,
                    "bug.fixed_in",
                    "fixed_in is allowed only with resolution fixed",
                    rel,
                )

    sentinel_metadata = dict(metadata)
    if expected_type == "bug" and is_unreleased_sentinel(
        metadata.get("found_in")
    ):
        sentinel_metadata.pop("found_in", None)
    if contains_unreleased_sentinel(sentinel_metadata):
        add_finding(
            findings,
            "version.sentinel_scope",
            "unreleased 仅允许出现在 Bug found_in",
            rel,
        )
