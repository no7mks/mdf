import re
from pathlib import Path

from .constants import (
    BUG_TERMINAL_RESOLUTIONS,
    CHANGE_KINDS,
    MARKER_RE,
    contains_unreleased_sentinel,
)
from .errors import Finding, MDFError, add_finding
from .gitutil import branch_details
from .paths import path_stays_in_repo, relative
from .textutil import stable_semver
from .validate_objects import required_sections
from .yamlutil import read_frontmatter


def validate_change_file(
    repo: Path,
    path: Path,
    findings: list[Finding],
    *,
    expected_slug: str,
    root: bool = False,
) -> None:
    rel = relative(repo, path)
    try:
        metadata, body = read_frontmatter(path)
    except MDFError as exc:
        add_finding(findings, "change.frontmatter", str(exc), rel)
        return
    change_kind = metadata.get("change_kind")
    if change_kind not in CHANGE_KINDS:
        add_finding(
            findings,
            "change.kind",
            "CHANGE requires change_kind feature, bugfix, release, or hotfix",
            rel,
        )
    source_branch = metadata.get("source_branch")
    if not isinstance(source_branch, str):
        add_finding(
            findings,
            "change.source_branch",
            "CHANGE requires source_branch",
            rel,
        )
    else:
        try:
            details = branch_details(source_branch)
        except MDFError as exc:
            add_finding(findings, "change.source_branch", str(exc), rel)
        else:
            expected_kinds = (
                {"release", "hotfix"} if root else {"feature", "bugfix"}
            )
            if (
                not details["supported"]
                or details["kind"] not in expected_kinds
            ):
                add_finding(
                    findings,
                    "change.source_branch",
                    "CHANGE source_branch does not match its directory role",
                    rel,
                )
            elif change_kind != details["kind"]:
                add_finding(
                    findings,
                    "change.kind",
                    "change_kind must match source_branch",
                    rel,
                )
            elif not root and details["slug"] != expected_slug:
                add_finding(
                    findings,
                    "change.slug",
                    "CHANGE directory slug does not match source_branch",
                    rel,
                )
    if root:
        if change_kind not in {"release", "hotfix"}:
            add_finding(
                findings,
                "change.kind",
                "Version-root CHANGE must be release or hotfix",
                rel,
            )
        if (
            not isinstance(metadata.get("version"), str)
            or metadata.get("version") != expected_slug
        ):
            add_finding(
                findings,
                "change.version",
                "Version-root CHANGE version must equal its directory",
                rel,
            )
        previous = metadata.get("previous_version")
        if previous not in (None, "none") and stable_semver(previous) is None:
            add_finding(
                findings,
                "change.previous_version",
                "previous_version must be a stable SemVer or none",
                rel,
            )
        if metadata.get("audit") != "passed":
            add_finding(
                findings,
                "change.audit",
                "Version-root CHANGE audit must be passed",
                rel,
            )
        included = metadata.get("included_changes")
        if not isinstance(included, list) or any(
            not isinstance(item, str) for item in included
        ):
            add_finding(
                findings,
                "change.included",
                "included_changes must be a string list",
                rel,
            )
    for key in ("requirements", "fixed", "closed", "deferred", "adrs"):
        if not isinstance(metadata.get(key), list):
            add_finding(
                findings,
                "change.links",
                f"{key} must be a list",
                rel,
            )
    if "bugs" in metadata:
        add_finding(
            findings,
            "change.bugs_renamed",
            "请使用 fixed、closed 或 deferred，而不是 bugs",
            rel,
        )
    bug_lists = [metadata.get(key) for key in ("fixed", "closed", "deferred")]
    bug_ids = [
        item
        for values in bug_lists
        if isinstance(values, list)
        for item in values
    ]
    if any(not isinstance(item, str) for item in bug_ids):
        add_finding(
            findings, "change.links", "Bug outcome 列表元素必须是字符串", rel
        )
        bug_ids = [item for item in bug_ids if isinstance(item, str)]
    if len(bug_ids) != len(set(bug_ids)):
        add_finding(
            findings,
            "change.bug_duplicate",
            "同一 Bug ID 只能出现在一个 outcome 列表中",
            rel,
        )
    closed_resolutions = metadata.get("closed_resolutions")
    if closed_resolutions is not None:
        if not isinstance(closed_resolutions, dict) or any(
            not isinstance(identifier, str)
            or not isinstance(value, str)
            or value not in BUG_TERMINAL_RESOLUTIONS
            for identifier, value in closed_resolutions.items()
        ):
            add_finding(
                findings,
                "change.closed_resolutions",
                "closed_resolutions 必须将 Bug ID 映射到非 fixed 终态 resolution",
                rel,
            )
        elif isinstance(metadata.get("closed"), list) and set(
            closed_resolutions
        ) != {item for item in metadata["closed"] if isinstance(item, str)}:
            add_finding(
                findings,
                "change.closed_resolutions",
                "closed_resolutions 必须精确覆盖 closed Bug ID",
                rel,
            )
    elif metadata.get("closed"):
        add_finding(
            findings,
            "change.closed_resolutions",
            "closed Bug 需要显式终态 resolution",
            rel,
        )
    release_notes = metadata.get("release_notes")
    categories = {
        "Added",
        "Changed",
        "Deprecated",
        "Removed",
        "Fixed",
        "Security",
    }
    if release_notes == "none":
        pass
    elif isinstance(release_notes, dict):
        unknown = set(release_notes) - categories
        populated = [
            value
            for value in release_notes.values()
            if isinstance(value, list) and value
        ]
        if (
            unknown
            or not populated
            or any(
                not isinstance(value, list)
                or any(
                    not isinstance(item, str) or not item.strip()
                    for item in value
                )
                for value in release_notes.values()
            )
        ):
            add_finding(
                findings,
                "change.release_notes",
                "release_notes must use non-empty Keep a Changelog categories",
                rel,
            )
    else:
        add_finding(
            findings,
            "change.release_notes",
            "release_notes must be the scalar none or a category mapping",
            rel,
        )
    if not isinstance(metadata.get("breaking"), bool):
        add_finding(
            findings, "change.breaking", "breaking must be boolean", rel
        )
    elif (
        isinstance(release_notes, dict)
        and "Removed" in release_notes
        and metadata.get("breaking") is not True
    ):
        add_finding(
            findings,
            "change.removed_breaking",
            "A Removed release note requires breaking: true",
            rel,
        )
    evidence = metadata.get("evidence")
    if not isinstance(evidence, dict):
        add_finding(
            findings, "change.evidence", "evidence must be a mapping", rel
        )
    else:
        for key in ("tests", "commands", "artifacts"):
            if not isinstance(evidence.get(key), list):
                add_finding(
                    findings,
                    "change.evidence",
                    f"evidence.{key} must be a list",
                    rel,
                )
    if contains_unreleased_sentinel(metadata):
        add_finding(
            findings,
            "version.sentinel_scope",
            "unreleased is forbidden in CHANGE metadata",
            rel,
        )
    if MARKER_RE.search(body):
        add_finding(
            findings,
            "change.marker",
            "CHANGE contains an unresolved template marker",
            rel,
        )
    sections = [
        "Result",
        "Current Docs Updated",
        "Migration",
        "Known Deviations",
    ]
    if root:
        sections.extend(
            [
                "Included Changes",
                "Closeout Outcomes",
                "Found-in Transitions",
                "SemVer Decision",
                "Audit",
                "Validation Commands",
            ]
        )
    required_sections(body, sections, rel, findings)


def validate_version_change_file(
    repo: Path, path: Path, findings: list[Finding], version: str
) -> None:
    validate_change_file(repo, path, findings, expected_slug=version, root=True)


def validate_changes(repo: Path, findings: list[Finding]) -> None:
    root = repo / "changes"
    if (
        not root.is_dir()
        or root.is_symlink()
        or not path_stays_in_repo(repo, root)
    ):
        return
    for directory in sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and not path.is_symlink()
        and path_stays_in_repo(repo, path)
    ):
        if directory.name == "unreleased":
            for change_dir in sorted(
                path
                for path in directory.iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and path_stays_in_repo(repo, path)
            ):
                if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", change_dir.name):
                    add_finding(
                        findings,
                        "change.directory",
                        "Unreleased change directory must be an ASCII kebab-case slug",
                        relative(repo, change_dir),
                    )
                change = change_dir / "CHANGE.md"
                if not change.is_file():
                    add_finding(
                        findings,
                        "change.missing",
                        "unreleased Change 目录需要 CHANGE.md",
                        relative(repo, change_dir),
                    )
                else:
                    validate_change_file(
                        repo,
                        change,
                        findings,
                        expected_slug=change_dir.name,
                    )
            continue
        if stable_semver(directory.name) is None:
            add_finding(
                findings,
                "release.directory",
                "Released change directory must be a stable SemVer",
                relative(repo, directory),
            )
            continue
        legacy_release = directory / "RELEASE.md"
        if legacy_release.exists():
            add_finding(
                findings,
                "release.legacy_file",
                "RELEASE.md 已废弃；请使用版本根 CHANGE.md",
                relative(repo, legacy_release),
            )
        release = directory / "CHANGE.md"
        if not release.is_file():
            add_finding(
                findings,
                "release.missing",
                "已发布版本目录需要根 CHANGE.md",
                relative(repo, directory),
            )
        else:
            validate_version_change_file(
                repo, release, findings, directory.name
            )
            try:
                root_metadata, _ = read_frontmatter(release)
            except MDFError:
                root_metadata = {}
            root_kind = root_metadata.get("change_kind")
            child_dirs = sorted(
                path.name
                for path in directory.iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and path_stays_in_repo(repo, path)
            )
            included_changes = root_metadata.get("included_changes")
            if isinstance(included_changes, list):
                if any(not isinstance(item, str) for item in included_changes):
                    add_finding(
                        findings,
                        "release.included_changes",
                        "版本根 included_changes 必须是字符串列表",
                        relative(repo, release),
                    )
                elif sorted(included_changes) != child_dirs:
                    add_finding(
                        findings,
                        "release.included_changes",
                        "版本根 included_changes 必须等于其子 Change 目录",
                        relative(repo, release),
                    )
            aggregate: dict[str, set[str]] = {
                key: set()
                for key in (
                    "requirements",
                    "fixed",
                    "closed",
                    "deferred",
                    "adrs",
                )
            }
            aggregate_resolutions: dict[str, str] = {}
            for child_dir in child_dirs:
                child = directory / child_dir / "CHANGE.md"
                if not child.is_file():
                    continue
                try:
                    child_metadata, _ = read_frontmatter(child)
                except MDFError:
                    continue
                for key in aggregate:
                    values = child_metadata.get(key)
                    if isinstance(values, list):
                        aggregate[key].update(str(value) for value in values)
                raw_resolutions = child_metadata.get("closed_resolutions")
                if isinstance(raw_resolutions, dict):
                    aggregate_resolutions.update(
                        {
                            str(key): str(value)
                            for key, value in raw_resolutions.items()
                        }
                    )
            # A hotfix is a direct version-level Change: it intentionally has
            # no unreleased child slug to aggregate. Release roots must include
            # every child outcome and may supersets from release-level closures.
            if not (root_kind == "hotfix" and not child_dirs):
                for key, values in aggregate.items():
                    root_values = root_metadata.get(key)
                    if not isinstance(root_values, list):
                        if values:
                            add_finding(
                                findings,
                                "release.aggregate",
                                f"版本根 {key} 必须包含子 Change outcomes",
                                relative(repo, release),
                            )
                        continue
                    root_set = {str(value) for value in root_values}
                    if not values.issubset(root_set):
                        add_finding(
                            findings,
                            "release.aggregate",
                            f"版本根 {key} 必须覆盖全部子 Change outcome",
                            relative(repo, release),
                        )
                if aggregate_resolutions:
                    root_resolutions = root_metadata.get("closed_resolutions")
                    if not isinstance(root_resolutions, dict):
                        add_finding(
                            findings,
                            "release.aggregate",
                            "版本根 closed_resolutions 必须覆盖子 Change 的 resolutions",
                            relative(repo, release),
                        )
                    else:
                        for (
                            identifier,
                            resolution,
                        ) in aggregate_resolutions.items():
                            if root_resolutions.get(identifier) != resolution:
                                add_finding(
                                    findings,
                                    "release.aggregate",
                                    "版本根 closed_resolutions 必须覆盖子 Change 的 resolutions",
                                    relative(repo, release),
                                )
                                break
        for change_dir in sorted(
            path
            for path in directory.iterdir()
            if path.is_dir()
            and not path.is_symlink()
            and path_stays_in_repo(repo, path)
        ):
            change = change_dir / "CHANGE.md"
            if not change.is_file():
                add_finding(
                    findings,
                    "change.missing",
                    "已发布 Change 快照需要 CHANGE.md",
                    relative(repo, change_dir),
                )
            else:
                validate_change_file(
                    repo,
                    change,
                    findings,
                    expected_slug=change_dir.name,
                )
