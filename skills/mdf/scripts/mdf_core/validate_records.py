import re
from pathlib import Path

from .constants import MARKER_RE
from .errors import Finding, MDFError, add_finding
from .paths import path_stays_in_repo, relative
from .validate_objects import iter_object_files
from .yamlutil import read_frontmatter


def validate_adrs(repo: Path, findings: list[Finding]) -> None:
    root = repo / "docs" / "adr"
    if (
        not root.is_dir()
        or root.is_symlink()
        or not path_stays_in_repo(repo, root)
    ):
        return
    for path in sorted(root.glob("*.md")):
        if path.is_symlink() or not path_stays_in_repo(repo, path):
            continue
        rel = relative(repo, path)
        match = re.fullmatch(r"(\d{4})-([a-z0-9][a-z0-9-]*)\.md", path.name)
        if not match:
            add_finding(
                findings,
                "adr.filename",
                "ADR filename must be NNNN-ascii-kebab-case.md",
                rel,
            )
            continue
        try:
            metadata, body = read_frontmatter(path)
        except MDFError as exc:
            add_finding(findings, "adr.frontmatter", str(exc), rel)
            continue
        if metadata.get("id") != f"adr-{match.group(1)}":
            add_finding(
                findings,
                "adr.id",
                f"ADR id must equal adr-{match.group(1)}",
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


def validate_record_references(repo: Path, findings: list[Finding]) -> None:
    known: set[str] = set()
    identifier_paths: dict[str, Path] = {}
    proposals: dict[str, dict] = {}
    object_paths: list[Path] = []
    for kind in ("proposal", "bug"):
        for path in iter_object_files(repo, kind):
            object_paths.append(path)
            try:
                metadata, _ = read_frontmatter(path)
            except MDFError:
                continue
            identifier = metadata.get("id")
            if isinstance(identifier, str):
                if identifier in identifier_paths:
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
    adr_root = repo / "docs" / "adr"
    if adr_root.is_dir():
        for path in adr_root.glob("*.md"):
            if path.is_symlink() or not path_stays_in_repo(repo, path):
                continue
            match = re.fullmatch(r"(\d{4})-[a-z0-9][a-z0-9-]*\.md", path.name)
            if match:
                known.add(f"adr-{match.group(1)}")

    validate_proposal_dependencies(
        repo,
        known,
        proposals,
        identifier_paths,
        findings,
    )

    replacements = {}
    for identifier, metadata in proposals.items():
        values = metadata.get("replaced_by", [])
        if not isinstance(values, list):
            continue
        replacements[identifier] = {value for value in values if isinstance(value, str)}
        if any(value not in proposals or value == identifier for value in replacements[identifier]):
            add_finding(findings, "proposal.replaced_by", "替代关系引用无效",
                        relative(repo, identifier_paths[identifier]))
    for identifier in cyclic_proposals(replacements):
        add_finding(findings, "proposal.replacement_cycle", "替代关系不得成环",
                    relative(repo, identifier_paths[identifier]))

    for path in object_paths:
        try:
            metadata, _ = read_frontmatter(path)
        except MDFError:
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
                    primary_metadata, _ = read_frontmatter(primary_path)
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

    changes = repo / "docs/changes"
    if not changes.is_dir():
        return
    for path in changes.rglob("CHANGE.md"):
        if path.is_symlink() or not path_stays_in_repo(repo, path):
            continue
        try:
            metadata, _ = read_frontmatter(path)
        except MDFError:
            continue
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
                if (
                    not isinstance(identifier, str)
                    or not identifier.startswith(prefix)
                    or identifier not in known
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
                            record_metadata, _ = read_frontmatter(record_path)
                        except MDFError:
                            record_metadata = {}
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


def validate_proposal_dependencies(
    repo: Path,
    known: set[str],
    proposals: dict[str, dict],
    identifier_paths: dict[str, Path],
    findings: list[Finding],
) -> None:
    dependencies: dict[str, set[str]] = {}
    for identifier, metadata in proposals.items():
        path = identifier_paths[identifier]
        rel = relative(repo, path)
        depends_on = metadata.get("depends_on")
        if not isinstance(depends_on, list):
            continue
        dependencies[identifier] = set()
        for dependency in depends_on:
            if not isinstance(dependency, str):
                add_finding(
                    findings,
                    "proposal.depends_on_type",
                    "Proposal depends_on entries must be Proposal IDs",
                    rel,
                )
                continue
            if dependency == identifier:
                add_finding(
                    findings,
                    "proposal.depends_on_self",
                    "A Proposal cannot depend on itself",
                    rel,
                )
                continue
            target = proposals.get(dependency)
            if target is None:
                code = (
                    "object.depends_on_missing"
                    if dependency not in known
                    else "proposal.depends_on_type"
                )
                add_finding(
                    findings,
                    code,
                    "Proposal dependency must be an active Proposal: "
                    f"{dependency}",
                    rel,
                )
                continue
            status = target.get("status")
            released = (
                status in {"implemented", "released"}
            )
            if status not in {"draft", "ready"} and not released:
                add_finding(
                    findings,
                    "proposal.depends_on_unreleased",
                    "Proposal dependency must be active or released: "
                    f"{dependency}",
                    rel,
                )
                continue
            dependencies[identifier].add(dependency)
    for identifier in sorted(cyclic_proposals(dependencies)):
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
