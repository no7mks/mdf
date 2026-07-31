from pathlib import Path
from typing import Any

from .archive import archive_plan
from .closeout_render import (
    active_objects,
    aggregate_release_changes,
    close_object_text,
    render_version_change,
    update_changelog_text,
    update_manifest_release,
)
from .constants import (
    BUG_SEVERITIES,
    BUG_TERMINAL_RESOLUTIONS,
    CHANGELOG_CATEGORIES,
    OBJECT_FILE_RE,
    REQUIREMENT_CLOSED_RESOLUTIONS,
    is_unreleased_sentinel,
)
from .errors import Finding, MDFError, add_finding, serialize_findings
from .moves import (
    apply_moves_and_rewrites,
    moved_destination,
    opaque_links_survive_move,
    replacement_plan,
)
from .paths import manifest_path, relative
from .semver import bump_kind, required_bump
from .closeout_summary import summarize_closeout
from .validate_changes import validate_change_file
from .validate_links import validate_links
from .validate_records import validate_record_references
from .yamlutil import read_frontmatter


def apply_closeout(
    repo: Path,
    context: dict[str, Any],
) -> dict[str, Any]:
    all_slugs = [item["slug"] for item in context["release_items"]]
    change_findings: list[Finding] = []
    for slug in all_slugs:
        change_path = repo / "changes" / "unreleased" / slug / "CHANGE.md"
        if not change_path.is_file():
            add_finding(
                change_findings,
                "change.missing",
                "Release-set directory requires CHANGE.md",
                f"changes/unreleased/{slug}",
            )
            continue
        validate_change_file(
            repo,
            change_path,
            change_findings,
            expected_slug=slug,
        )
    validate_record_references(repo, change_findings)
    validate_links(repo, change_findings)
    if change_findings:
        raise MDFError(
            "Release set is invalid",
            code="invalid_release_set",
            details={"findings": serialize_findings(change_findings)},
        )

    if context["mode"] == "hotfix":
        hotfix_change = context.get("hotfix_change") or {}
        if not isinstance(hotfix_change, dict):
            raise MDFError(
                "hotfix_change 必须是内存对象", code="invalid_closeout_spec"
            )
        notes = {category: [] for category in CHANGELOG_CATEGORIES}
        raw_notes = hotfix_change.get("release_notes")
        if isinstance(raw_notes, dict):
            for category in CHANGELOG_CATEGORIES:
                values = raw_notes.get(category, [])
                if isinstance(values, list):
                    notes[category] = [str(value) for value in values]
        breaking = hotfix_change.get("breaking") is True
        requirement_ids = set(hotfix_change.get("requirements", []))
        fixed_ids = set(hotfix_change.get("fixed", []))
        closed_ids = set(hotfix_change.get("closed", []))
        deferred_ids = set(hotfix_change.get("deferred", []))
        adrs = set(hotfix_change.get("adrs", []))
        closed_resolutions = (
            dict(hotfix_change.get("closed_resolutions", {}))
            if isinstance(hotfix_change.get("closed_resolutions", {}), dict)
            else {}
        )
        if any(
            not isinstance(value, str) or value not in BUG_TERMINAL_RESOLUTIONS
            for value in closed_resolutions.values()
        ):
            raise MDFError(
                "hotfix closed_resolutions 的值必须是非 fixed 终态 resolution",
                code="invalid_closeout_spec",
            )
        if closed_ids and set(closed_resolutions) != closed_ids:
            raise MDFError(
                "hotfix closed_resolutions 必须精确覆盖 closed Bug ID",
                code="invalid_closeout_spec",
            )
        hotfix_body = (
            hotfix_change.get("body")
            if isinstance(hotfix_change.get("body"), str)
            else "Hotfix result verified."
        )
    else:
        (
            notes,
            breaking,
            requirement_ids,
            fixed_ids,
            closed_ids,
            deferred_ids,
            adrs,
            closed_resolutions,
        ) = aggregate_release_changes(repo, all_slugs)
        hotfix_body = None
    if (
        fixed_ids & closed_ids
        or fixed_ids & deferred_ids
        or closed_ids & deferred_ids
    ):
        raise MDFError(
            "每个 Bug 只能出现在 fixed、closed、deferred 之一",
            code="change_outcome_overlap",
        )
    bug_ids = fixed_ids | closed_ids | deferred_ids
    baseline_closures = requirement_ids | bug_ids
    closures = context["closures"]
    closure_ids = {closure["id"] for closure in closures}
    if not baseline_closures.issubset(closure_ids):
        raise MDFError(
            "closures 必须覆盖 Change 声明的全部 Requirement 与 Bug outcome",
            code="closure_set_mismatch",
            details={
                "expected_minimum": sorted(baseline_closures),
                "specified": sorted(closure_ids),
                "missing": sorted(baseline_closures - closure_ids),
            },
        )
    objects = active_objects(repo)
    closed_requirement_resolutions: dict[str, str] = {}
    for closure in closures:
        identifier = closure["id"]
        resolution = closure.get("resolution")
        if identifier in requirement_ids and resolution != "fulfilled":
            raise MDFError(
                f"Requirement closeout must use fulfilled: {identifier}",
                code="invalid_closure",
            )
        if identifier in fixed_ids and resolution != "fixed":
            raise MDFError(
                f"Fixed Bug must use fixed resolution: {identifier}",
                code="invalid_closure",
            )
        if identifier in deferred_ids and resolution != "deferred":
            raise MDFError(
                f"Deferred Bug must use deferred outcome: {identifier}",
                code="invalid_closure",
            )
        if (
            identifier in closed_ids
            and resolution not in BUG_TERMINAL_RESOLUTIONS
        ):
            raise MDFError(
                f"Closed Bug must use a terminal non-fixed resolution: {identifier}",
                code="invalid_closure",
            )
        if identifier not in baseline_closures:
            record = objects.get(identifier)
            object_kind = record[0] if record is not None else None
            if resolution == "fixed":
                fixed_ids.add(identifier)
            elif resolution == "deferred":
                deferred_ids.add(identifier)
            elif resolution == "fulfilled":
                requirement_ids.add(identifier)
            elif (
                resolution in REQUIREMENT_CLOSED_RESOLUTIONS
                and object_kind == "requirement"
            ):
                closed_requirement_resolutions[identifier] = resolution
            elif (
                resolution in BUG_TERMINAL_RESOLUTIONS
                and object_kind != "requirement"
            ):
                closed_ids.add(identifier)
                closed_resolutions.setdefault(identifier, resolution)
            else:
                raise MDFError(
                    f"Supplemental closure has unsupported resolution: {identifier}",
                    code="invalid_closure",
                )
    unreleased_ready = sorted(
        identifier
        for identifier, (kind, _path, metadata) in objects.items()
        if kind == "bug"
        and metadata.get("status") == "ready"
        and is_unreleased_sentinel(metadata.get("found_in"))
        and metadata.get("resolution") != "duplicate"
    )
    classified_bugs = {
        closure["id"]
        for closure in closures
        if closure["id"].startswith("bug-")
    }
    missing_unreleased = [
        identifier
        for identifier in unreleased_ready
        if identifier not in classified_bugs
    ]
    if missing_unreleased:
        raise MDFError(
            "每个 ready 且 found_in: unreleased 的 Bug 必须出现在 closeout outcomes 中",
            code="unclassified_unreleased_bug",
            details={"missing": missing_unreleased},
        )
    for closure in closures:
        identifier = closure["id"]
        record = objects.get(identifier)
        if record is None:
            raise MDFError(
                f"Closure object is not an active canonical object: {identifier}",
                code="invalid_closure",
            )
        kind, path, metadata = record
        expected_kind = (
            "requirement"
            if identifier in requirement_ids
            or identifier in closed_requirement_resolutions
            else "bug"
        )
        if kind != expected_kind or metadata.get("status") != "ready":
            raise MDFError(
                f"Closure object has the wrong type or state: {identifier}",
                code="invalid_closure",
            )
        if kind == "bug" and metadata.get("resolution") == "duplicate":
            raise MDFError(
                "duplicate Bug 不得进入 Change outcomes；请改用 canonical Bug ID",
                code="duplicate_in_changeset",
            )
        if kind == "bug":
            severity = metadata.get("severity")
            resolution = closure["resolution"]
            if (
                resolution == "deferred"
                or resolution in BUG_TERMINAL_RESOLUTIONS
            ) and severity == "critical":
                raise MDFError(
                    f"critical Bug 只能 fixed: {identifier}",
                    code="critical_bug_blocks_release",
                )
            if resolution == "deferred" and severity not in BUG_SEVERITIES:
                raise MDFError(
                    f"Deferred Bug has no valid severity: {identifier}",
                    code="invalid_closure",
                )
            if resolution in {"deferred", "wont-fix"} and severity == "major":
                acceptance = context.get("deferred_acceptance", {})
                item = (
                    acceptance.get(identifier)
                    if isinstance(acceptance, dict)
                    else None
                )
                if (
                    not isinstance(item, dict)
                    or not item.get("accepted")
                    or not str(item.get("reason", "")).strip()
                    or not str(item.get("follow_up", "")).strip()
                ):
                    raise MDFError(
                        f"major Bug 需要明确接受、理由与 follow-up: {identifier}",
                        code="severity_gate",
                    )
        original = path.read_text(encoding="utf-8")
        updated = close_object_text(
            original,
            kind=kind,
            closure=closure,
            version=context["version"],
        )
        path.write_text(updated, encoding="utf-8")

    # A deferred Bug remains ready and is intentionally not archived.  All
    # other processed objects are closed by close_object_text above.

    categories = {
        category for category in CHANGELOG_CATEGORIES if notes[category]
    }
    previous_tuple = context["previous_tuple"]
    candidate = context["candidate"]
    actual_bump = bump_kind(previous_tuple, candidate)
    minimum_bump = required_bump(
        previous_tuple,
        categories or {"none"},
        breaking,
    )
    rank = {"patch": 1, "minor": 2, "major": 3}
    if rank[actual_bump] < rank[minimum_bump]:
        raise MDFError(
            (
                f"Release uses a {actual_bump} bump but the Change set "
                f"requires at least {minimum_bump}"
            ),
            code="insufficient_bump",
        )

    release_dir = repo / "changes" / context["version"]
    moves: dict[Path, Path] = {}
    move_records: list[dict[str, Any]] = []
    for item in context["release_items"]:
        source = repo / item["source"]
        destination = release_dir / item["slug"]
        broken = opaque_links_survive_move(repo, source, destination)
        if broken:
            raise MDFError(
                "Moving the Change would break an opaque Markdown link",
                code="opaque_link_would_break",
                details={"links": broken},
            )
        moves[source] = destination
        move_records.append(
            {
                "kind": "repo",
                "from": item["source"],
                "to": relative(repo, destination),
            }
        )
    epoch = ".".join(context["version"].split(".")[:2])
    archive_moves, _ = archive_plan(repo, epoch)
    archived: list[tuple[str, str]] = []
    for source, destination in archive_moves.items():
        metadata, _ = read_frontmatter(source)
        identifier = metadata.get("id")
        if isinstance(identifier, str):
            archived.append((identifier, relative(repo, destination)))
        moves[source] = destination
        move_records.append(
            {
                "kind": "repo",
                "from": relative(repo, source),
                "to": relative(repo, destination),
            }
        )

    rewrites = replacement_plan(
        repo,
        moves,
        rewrite_inside_sources=False,
        rewrite_inside_filter=lambda path: (
            path.name == "CHANGE.md"
            or (
                path.relative_to(repo).parts[0] in {"requirements", "bugs"}
                and OBJECT_FILE_RE.fullmatch(path.name) is not None
            )
        ),
    )
    apply_moves_and_rewrites(moves, rewrites)

    release_dir.mkdir(parents=True, exist_ok=True)
    release_path = release_dir / "CHANGE.md"
    found_in_transitions: list[str] = []
    for closure in closures:
        if (
            not closure["id"].startswith("bug-")
            or closure["resolution"] == "duplicate"
        ):
            continue
        record = objects.get(closure["id"])
        if record is not None and is_unreleased_sentinel(
            record[2].get("found_in")
        ):
            found_in_transitions.append(
                f"{closure['id']}: unreleased -> {context['version']}"
            )
    release_path.write_text(
        render_version_change(
            context["version"],
            context["previous"],
            context["release_date"],
            context["mode"],
            all_slugs,
            categories,
            breaking,
            minimum_bump,
            actual_bump,
            context["attestation"]["validation_commands"],
            requirement_ids,
            fixed_ids,
            closed_ids,
            deferred_ids,
            adrs,
            closed_resolutions,
            closed_requirement_resolutions,
            found_in_transitions,
            context.get("deferred_acceptance", {}),
            hotfix_body,
            release_notes=notes,
            verify_command_results=context.get("verify_command_results") or [],
            semantic_summary=(
                context["attestation"].get("summary")
                if isinstance(context.get("attestation"), dict)
                else None
            ),
        ),
        encoding="utf-8",
    )
    changelog_path = repo / "CHANGELOG.md"
    changelog_path.write_text(
        update_changelog_text(
            changelog_path.read_text(encoding="utf-8"),
            version=context["version"],
            release_date=context["release_date"],
            notes=notes,
        ),
        encoding="utf-8",
    )
    manifest = manifest_path(repo)
    manifest.write_text(
        update_manifest_release(
            manifest.read_text(encoding="utf-8"),
            context["version"],
        ),
        encoding="utf-8",
    )

    return {
        "slugs": sorted(all_slugs),
        "moves": sorted(move_records, key=lambda item: item["to"]),
        "archived": [
            {"id": identifier, "path": path}
            for identifier, path in sorted(archived)
        ],
        "semver": {
            "categories": sorted(categories),
            "breaking": breaking,
            "required_bump": minimum_bump,
            "actual_bump": actual_bump,
        },
        "rewrites": [
            relative(repo, moved_destination(path, moves))
            for path in sorted(rewrites)
        ],
        "outcomes": {
            "requirements": sorted(requirement_ids),
            "fixed": sorted(fixed_ids),
            "closed": sorted(closed_ids),
            "deferred": sorted(deferred_ids),
            "closed_resolutions": closed_resolutions,
            "closed_requirements": closed_requirement_resolutions,
        },
    }
