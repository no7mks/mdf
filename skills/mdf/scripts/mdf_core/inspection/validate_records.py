from pathlib import Path

from mdf_core.foundation.constants import ADR_FILE_RE, ADR_ROOT, MARKER_RE, OBJECT_FILE_RE
from mdf_core.foundation.errors import Finding, MDFError, add_finding
from mdf_core.foundation.paths import path_stays_in_repo, relative
from mdf_core.foundation.textutil import is_object_id_slug
from mdf_core.inspection.validate_objects import iter_object_files
from mdf_core.foundation.yamlutil import read_frontmatter


def validate_adrs(repo: Path, findings: list[Finding], *, paths: set[Path] | None = None, scan=None) -> None:
    root = repo / ADR_ROOT
    if (
        not root.is_dir()
        or root.is_symlink()
        or not path_stays_in_repo(repo, root)
    ):
        return
    for path in sorted(root.glob("*.md")):
        if (paths is not None and path not in paths) or (scan is not None and not scan.contains(path)):
            continue
        if path.is_symlink() or not path_stays_in_repo(repo, path):
            continue
        rel = relative(repo, path)
        match = ADR_FILE_RE.fullmatch(path.name)
        if not match:
            add_finding(
                findings,
                "adr.filename",
                "ADR filename must be ascii-kebab-case.md",
                rel,
            )
            continue
        slug = match.group(1)
        if is_object_id_slug(slug):
            add_finding(
                findings,
                "adr.slug_id",
                "ADR filename slug must not match an object ID",
                rel,
            )
        try:
            metadata, body = read_frontmatter(path)
        except MDFError as exc:
            add_finding(findings, "adr.frontmatter", str(exc), rel)
            continue
        expected_id = f"adr-{slug}"
        if metadata.get("id") != expected_id:
            add_finding(
                findings,
                "adr.id",
                f"ADR id must equal {expected_id}",
                rel,
            )
        if metadata.get("type") not in (None, "adr"):
            add_finding(findings, "adr.type", "ADR type must be adr", rel)
        if metadata.get("status") not in (
            None,
            "accepted",
            "superseded",
            "deprecated",
        ):
            add_finding(
                findings,
                "adr.status",
                "ADR status must be accepted, superseded, or deprecated",
                rel,
            )
        if MARKER_RE.search(body):
            add_finding(
                findings,
                "adr.marker",
                "ADR contains an unresolved template marker",
                rel,
            )


def _trunk_bug_ids(repo: Path, path: Path, metadata: dict) -> set[str]:
    """只允许带 support 身份与对应处置的版本根 Change 引用 trunk Bug。"""
    from mdf_core.lifecycle.delivery_state import read_json
    from mdf_core.lifecycle.support_line import DISPOSITIONS, NEEDS_REASON, SHA_RE, trunk_bug
    from mdf_core.workspace.workflow_policy import is_github_flow
    version = metadata.get("version")
    source = metadata.get("source_branch")
    if (not isinstance(version, str) or path != repo / "changes" / version / "CHANGE.md"
            or not isinstance(source, str) or not is_github_flow(repo)):
        return set()
    if not source.startswith("hotfix/") and not (
            metadata.get("record_mode") == "post_hoc" and source == metadata.get("release_line") and source.startswith("support/")):
        return set()
    try:
        identity = read_json(path.parent / "delivery.json")
    except (MDFError, OSError):
        if (path.parent / "delivery.json").exists() or metadata.get("record_mode") not in {"ledgerless", "post_hoc"}:
            return set()
        line = metadata.get("release_line", "")
        if not isinstance(line, str):
            return set()
        identity = {"branch": source, "version": version, "base_branch": line,
                    "support": {"branch": line, "major_minor": line.removeprefix("support/")}}
    support = identity.get("support")
    base = identity.get("base_branch")
    if (identity.get("branch") != source or identity.get("version") != version
            or not isinstance(base, str) or not base.startswith("support/")
            or not isinstance(support, dict) or support.get("branch") != base
            or support.get("major_minor") != base.removeprefix("support/")
            or not version.startswith(base.removeprefix("support/") + ".")):
        return set()
    fixes = metadata.get("trunk_fixes")
    fixed = metadata.get("fixed")
    if not isinstance(fixes, list) or not isinstance(fixed, list):
        return set()
    ids = [item.get("bug_id") for item in fixes if isinstance(item, dict)]
    if (any(not isinstance(identifier, str) for identifier in [*ids, *fixed])
            or len(ids) != len(fixes) or len(set(ids)) != len(ids) or set(ids) != set(fixed)):
        return set()
    found = set()
    for item in fixes:
        disposition = item.get("trunk_disposition")
        if (disposition not in DISPOSITIONS or item.get("released_in") != version
                or (disposition in NEEDS_REASON and not str(item.get("reason", "")).strip())
                or (disposition == "backported" and not SHA_RE.fullmatch(str(item.get("source_commit", ""))))):
            continue
        try:
            trunk_bug(repo, item["bug_id"])
        except MDFError:
            continue
        found.add(item["bug_id"])
    return found


def validate_record_references(
    repo: Path, findings: list[Finding], *, paths: set[Path] | None = None,
    touched_ids: set[str] | None = None, scan=None,
) -> None:
    read = scan.frontmatter if scan is not None else read_frontmatter

    def selected(path, metadata):
        if paths is None or path in paths:
            return True
        values = [metadata.get(key) for key in ("depends_on", "replaced_by", "duplicate_of",
                  "proposals", "fixed", "closed", "deferred", "adrs")]
        return any(item in (touched_ids or set()) for value in values
                   for item in (value if isinstance(value, list) else [value]) if isinstance(item, str))

    known: set[str] = set()
    identifier_paths: dict[str, Path] = {}
    slug_paths: dict[str, Path] = {}
    proposals: dict[str, dict] = {}
    object_paths: list[Path] = []
    for kind in ("proposal", "bug"):
        for path in iter_object_files(repo, kind):
            if scan is not None and not scan.contains(path):
                continue
            object_paths.append(path)
            match = OBJECT_FILE_RE.fullmatch(path.name)
            if match and len(path.relative_to(repo / "docs").parts) == 2:
                slug = match.group(2)
                if slug in slug_paths and (paths is None or path in paths or slug_paths[slug] in paths):
                    add_finding(
                        findings,
                        "object.slug_duplicate",
                        (
                            f"Duplicate slug {slug}; first declared at "
                            f"{relative(repo, slug_paths[slug])}"
                        ),
                        relative(repo, path),
                    )
                else:
                    slug_paths[slug] = path
            try:
                metadata, _ = read(path)
            except MDFError:
                continue
            identifier = metadata.get("id")
            if isinstance(identifier, str):
                if identifier in identifier_paths and (paths is None or path in paths or identifier_paths[identifier] in paths):
                    add_finding(
                        findings,
                        "object.id_duplicate",
                        (
                            f"Duplicate ID {identifier}; first declared at "
                            f"{relative(repo, identifier_paths[identifier])}"
                        ),
                        relative(repo, path),
                    )
                else:
                    identifier_paths[identifier] = path
                    if metadata.get("type") == "proposal":
                        proposals[identifier] = metadata
                known.add(identifier)
    adr_root = repo / ADR_ROOT
    if adr_root.is_dir():
        for path in adr_root.glob("*.md"):
            if path.is_symlink() or not path_stays_in_repo(repo, path) or (scan is not None and not scan.contains(path)):
                continue
            match = ADR_FILE_RE.fullmatch(path.name)
            if match and not is_object_id_slug(match.group(1)):
                known.add(f"adr-{match.group(1)}")

    validate_proposal_dependencies(
        repo,
        known,
        proposals,
        identifier_paths,
        findings,
        selected={ident for ident, meta in proposals.items() if selected(identifier_paths[ident], meta)},
        paths=paths, touched_ids=touched_ids,
    )

    replacements = {}
    for identifier, metadata in proposals.items():
        values = metadata.get("replaced_by", [])
        if not isinstance(values, list):
            continue
        replacements[identifier] = {value for value in values if isinstance(value, str)}
        relevant = replacements[identifier] if paths is None or identifier_paths[identifier] in paths else (
            replacements[identifier] & (touched_ids or set()))
        if any(value not in proposals or value == identifier for value in relevant):
            add_finding(findings, "proposal.replaced_by", "替代关系引用无效",
                        relative(repo, identifier_paths[identifier]))
    for identifier in cyclic_proposals(replacements):
        if not selected(identifier_paths[identifier], proposals[identifier]):
            continue
        add_finding(findings, "proposal.replacement_cycle", "替代关系不得成环",
                    relative(repo, identifier_paths[identifier]))

    for path in object_paths:
        try:
            metadata, _ = read(path)
        except MDFError:
            continue
        primary = metadata.get("duplicate_of")
        if paths is not None and path not in paths and (
                not isinstance(primary, str) or primary not in (touched_ids or set())):
            continue
        if (
            metadata.get("status") == "rejected"
            and metadata.get("reject-reason") == "duplicate"
        ):
            identifier = metadata.get("id")
            primary = metadata.get("duplicate_of")
            if not isinstance(primary, str) or primary not in known:
                add_finding(
                    findings,
                    "bug.duplicate_missing",
                    f"Unknown duplicate primary: {primary}",
                    relative(repo, path),
                )
                continue
            if primary == identifier:
                add_finding(
                    findings,
                    "bug.duplicate_self",
                    "A Bug cannot duplicate itself",
                    relative(repo, path),
                )
            primary_path = identifier_paths.get(primary)
            if primary_path is not None:
                try:
                    primary_metadata, _ = read(primary_path)
                except MDFError:
                    primary_metadata = {}
                if primary_metadata.get("type") != metadata.get("type"):
                    add_finding(
                        findings,
                        "bug.duplicate_type",
                        "duplicate_of must point to a Bug",
                        relative(repo, path),
                    )
                if (
                    primary_metadata.get("status") == "rejected"
                    and primary_metadata.get("reject-reason") == "duplicate"
                ):
                    add_finding(
                        findings,
                        "bug.duplicate_chain",
                        "Duplicate Bugs must point directly to a canonical "
                        "non-duplicate Bug",
                        relative(repo, path),
                    )

    changes = repo / "changes"
    if not changes.is_dir():
        return
    for path in changes.rglob("CHANGE.md"):
        if path.is_symlink() or not path_stays_in_repo(repo, path) or (scan is not None and not scan.contains(path)):
            continue
        try:
            metadata, _ = read(path)
        except MDFError:
            continue
        trunk_bugs = _trunk_bug_ids(repo, path, metadata)
        for key, prefix in (
            ("proposals", "prp-"),
            ("fixed", "bug-"),
            ("closed", "bug-"),
            ("deferred", "bug-"),
            ("adrs", "adr-"),
        ):
            values = metadata.get(key)
            if not isinstance(values, list):
                continue
            for identifier in values:
                if paths is not None and path not in paths and (
                        not isinstance(identifier, str) or identifier not in (touched_ids or set())):
                    continue
                if (
                    not isinstance(identifier, str)
                    or not identifier.startswith(prefix)
                    or (identifier not in known and not (key == "fixed" and identifier in trunk_bugs))
                ):
                    add_finding(
                        findings,
                        "change.record_missing",
                        f"Unknown {key} record: {identifier}",
                        relative(repo, path),
                    )
                    continue
                if key in {"fixed", "closed", "deferred"}:
                    record_path = identifier_paths.get(identifier)
                    if record_path is not None:
                        try:
                            record_metadata, _ = read(record_path)
                        except MDFError:
                            record_metadata = {}
                        if (key == "fixed" and path.is_relative_to(changes / "unreleased")
                                and record_metadata.get("status") not in {"fixed", "closed"}):
                            add_finding(
                                findings, "change.fixed_status",
                                f"未发布 Change 的 fixed Bug {identifier} 必须为 fixed 或 closed",
                                relative(repo, path),
                            )
                        if (
                            record_metadata.get("status") == "rejected"
                            and record_metadata.get("reject-reason")
                            == "duplicate"
                        ):
                            add_finding(
                                findings,
                                "change.duplicate_in_outcome",
                                f"Duplicate Bug {identifier} must be excluded "
                                "from Change outcomes; use its canonical Bug "
                                "ID",
                                relative(repo, path),
                            )


def require_fixed_outcomes(repo: Path, source: str) -> None:
    """合入前复用引用校验，仅拦截当前 source 的未发布修复状态冲突。"""
    findings: list[Finding] = []
    validate_record_references(repo, findings)
    for finding in findings:
        if finding.code != "change.fixed_status":
            continue
        metadata, _ = read_frontmatter(repo / finding.path)
        if metadata.get("source_branch") == source:
            raise MDFError(finding.message, code=finding.code, details=finding.as_dict())


SATISFIED = {"implemented", "released"}
DELIVERABLE = {"draft", "ready", "implemented", "released"}


def proposal_milestones(proposals: dict[str, dict]) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for identifier, metadata in proposals.items():
        name = metadata.get("milestone")
        if isinstance(name, str) and name.strip():
            groups.setdefault(name, set()).add(identifier)
    return groups


def unsatisfied_depends_on(
    depends_on: list, proposals: dict[str, dict]
) -> list[str]:
    groups = proposal_milestones(proposals)
    blocked: list[str] = []
    for dependency in depends_on:
        if not isinstance(dependency, str):
            continue
        target = proposals.get(dependency)
        if target is not None:
            if target.get("status") not in SATISFIED:
                blocked.append(dependency)
            continue
        members = groups.get(dependency)
        if members is None or any(
            proposals[ident].get("status") in {"draft", "ready"}
            for ident in members
        ):
            blocked.append(dependency)
    return blocked


def validate_proposal_dependencies(
    repo: Path,
    known: set[str],
    proposals: dict[str, dict],
    identifier_paths: dict[str, Path],
    findings: list[Finding],
    *, selected: set[str] | None = None, paths: set[Path] | None = None,
    touched_ids: set[str] | None = None,
) -> None:
    groups = proposal_milestones(proposals)
    dependencies: dict[str, set[str]] = {}
    for identifier, metadata in proposals.items():
        path = identifier_paths[identifier]
        rel = relative(repo, path)
        depends_on = metadata.get("depends_on")
        if not isinstance(depends_on, list):
            continue
        dependencies[identifier] = set()
        for dependency in depends_on:
            target_findings = findings if paths is None or path in paths or (
                isinstance(dependency, str) and dependency in (touched_ids or set())) else []
            if not isinstance(dependency, str):
                add_finding(
                    target_findings,
                    "proposal.depends_on_type",
                    "Proposal depends_on entries must be Proposal IDs or "
                    "milestone names",
                    rel,
                )
                continue
            if dependency == identifier:
                add_finding(
                    target_findings,
                    "proposal.depends_on_self",
                    "A Proposal cannot depend on itself",
                    rel,
                )
                continue
            target = proposals.get(dependency)
            if target is not None:
                status = target.get("status")
                released = status in SATISFIED
                if status not in {"draft", "ready"} and not released:
                    add_finding(
                        target_findings,
                        "proposal.depends_on_unreleased",
                        "Proposal dependency must be active or released: "
                        f"{dependency}",
                        rel,
                    )
                    continue
                dependencies[identifier].add(dependency)
                continue
            if dependency in groups:
                members = {
                    ident for ident in groups[dependency]
                    if proposals[ident].get("status") in DELIVERABLE
                }
                dependencies[identifier].update(members)
                continue
            code = (
                "object.depends_on_missing"
                if dependency not in known
                else "proposal.depends_on_type"
            )
            add_finding(
                target_findings,
                code,
                "Proposal dependency must be an active Proposal or existing "
                f"milestone: {dependency}",
                rel,
            )
    for identifier in sorted(cyclic_proposals(dependencies)):
        if selected is not None and identifier not in selected:
            continue
        add_finding(
            findings,
            "proposal.depends_on_cycle",
            "Proposal dependencies must not form a cycle",
            relative(repo, identifier_paths[identifier]),
        )


def cyclic_proposals(dependencies: dict[str, set[str]]) -> set[str]:
    state: dict[str, int] = {}
    stack: list[str] = []
    cycles: set[str] = set()

    def visit(identifier: str) -> None:
        state[identifier] = 1
        stack.append(identifier)
        for dependency in sorted(dependencies.get(identifier, set())):
            if state.get(dependency) == 1:
                cycles.update(stack[stack.index(dependency) :])
            elif state.get(dependency, 0) == 0:
                visit(dependency)
        stack.pop()
        state[identifier] = 2

    for identifier in sorted(dependencies):
        if state.get(identifier, 0) == 0:
            visit(identifier)
    return cycles
