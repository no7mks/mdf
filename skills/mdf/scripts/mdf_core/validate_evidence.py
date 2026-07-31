import os
from pathlib import Path
from typing import Any, Iterable

from .constants import (
    DOC_TYPES,
    FACT_ROOTS,
    MARKER_RE,
    MDF_BLOCK_END,
    MDF_BLOCK_START,
    PRODUCT_DOC_TYPES,
    SYSTEM_DOC_TYPES,
)
from .errors import Finding, MDFError, add_finding
from .gitutil import (
    commit_is_after,
    git_last_commit,
    git_path_dirty,
    git_path_tracked,
)
from .paths import path_stays_in_repo, relative
from .yamlutil import read_frontmatter


def frontmatter_evidence(
    metadata: dict[str, Any],
) -> list[tuple[str, str | None]]:
    raw = metadata.get("evidence")
    result: list[tuple[str, str | None]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                result.append((item, None))
            elif isinstance(item, dict) and isinstance(item.get("path"), str):
                method = item.get("verification", item.get("verify"))
                result.append(
                    (item["path"], method if isinstance(method, str) else None)
                )
    elif isinstance(raw, dict):
        paths = raw.get("paths")
        method = raw.get("verification", raw.get("verify"))
        if isinstance(paths, list):
            for path in paths:
                if isinstance(path, str):
                    result.append(
                        (path, method if isinstance(method, str) else None)
                    )
    return result


def fact_documents(repo: Path) -> Iterable[Path]:
    found: set[Path] = set()
    for raw in FACT_ROOTS:
        root = repo / raw
        if root.is_symlink() or not path_stays_in_repo(repo, root):
            continue
        if root.is_dir():
            found.update(
                path
                for path in root.rglob("*.md")
                if path.is_file()
                and not path.is_symlink()
                and path_stays_in_repo(repo, path)
            )
        elif root.is_file():
            found.add(root)
    return sorted(found)


def validate_evidence(
    repo: Path,
    findings: list[Finding],
    *,
    check_staleness: bool,
) -> None:
    for doc in fact_documents(repo):
        rel = relative(repo, doc)
        try:
            metadata, body = read_frontmatter(doc)
        except MDFError as exc:
            add_finding(findings, "fact.frontmatter", str(exc), rel)
            continue
        if metadata.get("doc_type") not in DOC_TYPES:
            add_finding(
                findings,
                "fact.doc_type",
                "Fact document requires a supported doc_type",
                rel,
            )
        else:
            parts = Path(rel).parts
            expected_doc_type: str | None = None
            if len(parts) >= 4 and parts[:2] == ("docs", "product"):
                expected_doc_type = PRODUCT_DOC_TYPES.get(parts[2])
            elif len(parts) >= 3 and parts[:2] == ("docs", "system"):
                selector = parts[2]
                expected_doc_type = SYSTEM_DOC_TYPES.get(selector)
            if expected_doc_type is None:
                add_finding(
                    findings,
                    "fact.path",
                    "Fact document is outside a supported product/system view",
                    rel,
                )
            elif metadata.get("doc_type") != expected_doc_type:
                add_finding(
                    findings,
                    "fact.doc_type_path",
                    f"doc_type must be {expected_doc_type} at this path",
                    rel,
                )
        if MARKER_RE.search(body):
            add_finding(
                findings,
                "fact.marker",
                "Fact document contains an unresolved template marker",
                rel,
            )
        evidence = frontmatter_evidence(metadata)
        generated = metadata.get("generated")
        if not evidence:
            add_finding(
                findings,
                "evidence.missing",
                "Current-fact document needs at least one evidence path",
                rel,
            )
        doc_tracked = git_path_tracked(repo, doc) if check_staleness else True
        if check_staleness and not doc_tracked:
            add_finding(
                findings,
                "fact.untracked",
                "Current-fact document is not tracked by Git",
                rel,
            )
        doc_commit = git_last_commit(repo, doc) if check_staleness else None
        for evidence_path, method in evidence:
            raw_candidate = Path(evidence_path)
            candidate = (repo / raw_candidate).resolve()
            if raw_candidate.is_absolute():
                add_finding(
                    findings,
                    "evidence.outside_repo",
                    f"Evidence must be repository-relative: {evidence_path}",
                    rel,
                )
                continue
            try:
                candidate.relative_to(repo)
            except ValueError:
                add_finding(
                    findings,
                    "evidence.outside_repo",
                    f"Evidence is outside the repository: {evidence_path}",
                    rel,
                )
                continue
            if not candidate.exists():
                add_finding(
                    findings,
                    "evidence.missing_path",
                    f"Evidence path does not exist: {evidence_path}",
                    rel,
                )
                continue
            if not method:
                add_finding(
                    findings,
                    "evidence.verification",
                    f"Evidence lacks a verification method: {evidence_path}",
                    rel,
                )
            if not check_staleness:
                continue
            if not git_path_tracked(repo, candidate):
                add_finding(
                    findings,
                    "evidence.untracked",
                    f"Evidence is not tracked by Git: {evidence_path}",
                    rel,
                )
                continue
            evidence_commit = git_last_commit(repo, candidate)
            if git_path_dirty(repo, candidate) or doc_commit is None:
                add_finding(
                    findings,
                    "evidence.stale",
                    f"Evidence requires revalidation: {evidence_path}",
                    rel,
                )
            elif evidence_commit is not None and commit_is_after(
                repo, evidence_commit, doc_commit
            ):
                add_finding(
                    findings,
                    "evidence.stale",
                    f"Evidence changed after this document: {evidence_path}",
                    rel,
                )
        if isinstance(generated, dict):
            source = generated.get("source")
            generator = generated.get("generator")
            source_path: Path | None = None
            generator_path: Path | None = None
            if not isinstance(source, str) or not source.strip():
                add_finding(
                    findings,
                    "generated.source",
                    "Generated documents require generated.source",
                    rel,
                )
            else:
                raw_source = Path(source)
                source_path = (repo / raw_source).resolve()
                if raw_source.is_absolute() or not path_stays_in_repo(
                    repo, source_path
                ):
                    add_finding(
                        findings,
                        "generated.outside_repo",
                        "Generated source must be repository-relative: "
                        f"{source}",
                        rel,
                    )
                    source_path = None
                elif not source_path.exists():
                    add_finding(
                        findings,
                        "generated.source_missing",
                        f"Generated source does not exist: {source}",
                        rel,
                    )
                    source_path = None
                elif check_staleness and not git_path_tracked(
                    repo, source_path
                ):
                    add_finding(
                        findings,
                        "generated.untracked",
                        f"Generated source is not tracked by Git: {source}",
                        rel,
                    )
            if not isinstance(generator, str) or not generator.strip():
                add_finding(
                    findings,
                    "generated.generator",
                    "Generated documents require generated.generator",
                    rel,
                )
            else:
                raw_generator = Path(generator)
                generator_path = (repo / raw_generator).resolve()
                if raw_generator.is_absolute() or not path_stays_in_repo(
                    repo, generator_path
                ):
                    add_finding(
                        findings,
                        "generated.outside_repo",
                        f"Generator must be repository-relative: {generator}",
                        rel,
                    )
                    generator_path = None
                elif not generator_path.is_file():
                    add_finding(
                        findings,
                        "generated.generator_missing",
                        f"Generator does not exist: {generator}",
                        rel,
                    )
                    generator_path = None
                elif not os.access(generator_path, os.X_OK):
                    add_finding(
                        findings,
                        "generated.generator_not_executable",
                        f"Generator is not executable: {generator}",
                        rel,
                    )
                    generator_path = None
                elif check_staleness and not git_path_tracked(
                    repo, generator_path
                ):
                    add_finding(
                        findings,
                        "generated.untracked",
                        f"Generator is not tracked by Git: {generator}",
                        rel,
                    )
                    generator_path = None
            if check_staleness:
                for label, generated_path in (
                    ("source", source_path),
                    ("generator", generator_path),
                ):
                    if generated_path is None:
                        continue
                    generated_commit = git_last_commit(repo, generated_path)
                    if (
                        git_path_dirty(repo, generated_path)
                        or doc_commit is None
                        or generated_commit is None
                        or commit_is_after(repo, generated_commit, doc_commit)
                    ):
                        add_finding(
                            findings,
                            "generated.stale",
                            f"Generated {label} requires revalidation",
                            rel,
                        )


def validate_agents_block(repo: Path, findings: list[Finding]) -> None:
    path = repo / "AGENTS.md"
    if not path.is_file():
        add_finding(
            findings, "agents.missing", "Missing AGENTS.md", "AGENTS.md"
        )
        return
    if path.is_symlink() or not path_stays_in_repo(repo, path):
        add_finding(
            findings,
            "path.symlink",
            "AGENTS.md must be a regular repository file",
            "AGENTS.md",
        )
        return
    text = path.read_text(encoding="utf-8")
    starts = text.count(MDF_BLOCK_START)
    ends = text.count(MDF_BLOCK_END)
    if (
        starts != 1
        or ends != 1
        or text.index(MDF_BLOCK_START) > text.index(MDF_BLOCK_END)
    ):
        add_finding(
            findings,
            "agents.block",
            "AGENTS.md must contain exactly one valid MDF managed block",
            "AGENTS.md",
        )
