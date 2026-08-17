import argparse
from pathlib import Path
from typing import Any

from . import doctor
from .errors import Finding, MDFError, add_finding, emit, serialize_findings
from .gitutil import git_path_tracked, repo_path, require_git_root, run
from .paths import path_stays_in_repo, relative
from .validate_evidence import fact_documents, frontmatter_evidence
from .validate_manifest import implementation_roots
from .yamlutil import parse_yaml, read_frontmatter


IGNORE_PATH = ".mdf/audit-ignore.yaml"


def _tracked_files(repo: Path, roots: list[Path]) -> list[Path]:
    result = run(["git", "ls-files", "-z"], cwd=repo)
    paths = []
    for raw in result.stdout.split("\0"):
        if not raw:
            continue
        path = (repo / raw).resolve()
        if (
            path.is_file()
            and not path.is_symlink()
            and any(path == root or root in path.parents for root in roots)
        ):
            paths.append(path)
    return sorted(set(paths))


def _scope_paths(
    repo: Path,
    implementation_paths: list[str],
    document_paths: list[str],
    roots: list[Path],
    facts: set[Path],
    findings: list[Finding],
) -> tuple[list[Path], list[Path]]:
    implementation: list[Path] = []
    documents: list[Path] = []
    for raw in implementation_paths:
        candidate = Path(raw)
        path = (repo / candidate).resolve()
        if candidate.is_absolute() or not path_stays_in_repo(repo, path):
            add_finding(
                findings,
                "audit.scope_path",
                "scope path is outside repository",
                raw,
            )
            continue
        if (
            path.is_file()
            and not path.is_symlink()
            and git_path_tracked(repo, path)
            and any(root in path.parents for root in roots)
        ):
            implementation.append(path)
        else:
            add_finding(
                findings, "audit.scope_path", "scope path is invalid", raw
            )
    for raw in document_paths:
        candidate = Path(raw)
        path = (repo / candidate).resolve()
        if candidate.is_absolute() or not path_stays_in_repo(repo, path):
            add_finding(
                findings,
                "audit.scope_path",
                "scope path is outside repository",
                raw,
            )
        elif path in facts:
            documents.append(path)
        else:
            add_finding(
                findings, "audit.scope_path", "scope path is invalid", raw
            )
    return sorted(set(implementation)), sorted(set(documents))


def _ignored_paths(
    repo: Path, sources: list[Path], roots: list[Path], findings: list[Finding]
) -> dict[Path, dict[str, str]]:
    path = repo / IGNORE_PATH
    if (
        not path.is_file()
        or path.is_symlink()
        or not git_path_tracked(repo, path)
    ):
        add_finding(
            findings, "audit.ignore_file", "audit ignorelist must be tracked",
            IGNORE_PATH,
        )
        return {}
    try:
        raw = parse_yaml(path.read_text(encoding="utf-8"))
    except MDFError as exc:
        add_finding(findings, "audit.ignore_file", str(exc), IGNORE_PATH)
        return {}
    entries = raw.get("ignored") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        add_finding(
            findings, "audit.ignore_file", "ignored must be a list", IGNORE_PATH
        )
        return {}
    result: dict[Path, dict[str, str]] = {}
    seen: set[Path] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "reason"}:
            add_finding(
                findings,
                "audit.ignore_rule",
                "ignore rule needs path and reason",
                IGNORE_PATH,
            )
            continue
        raw_path, reason = entry["path"], entry["reason"]
        candidate = Path(raw_path) if isinstance(raw_path, str) else Path()
        target = (repo / candidate).resolve()
        if (
            not isinstance(raw_path, str)
            or not raw_path.strip()
            or candidate.is_absolute()
            or not path_stays_in_repo(repo, target)
            or not isinstance(reason, str)
            or not reason.strip()
            or not target.exists()
            or target.is_symlink()
            or not any(
                target == root or root in target.parents for root in roots
            )
        ):
            add_finding(
                findings, "audit.ignore_rule", "ignore rule is invalid",
                str(raw_path),
            )
            continue
        if target in seen:
            add_finding(
                findings,
                "audit.ignore_duplicate",
                "ignore rules must not repeat",
                raw_path,
            )
            continue
        seen.add(target)
        matched = [
            item for item in sources if item == target or target in item.parents
        ]
        if not matched:
            add_finding(
                findings, "audit.ignore_empty",
                "ignore rule matches no tracked implementation file", raw_path,
            )
            continue
        for item in matched:
            result[item] = {"path": raw_path, "reason": reason}
    return result


def audit_payload(
    repo: Path,
    scope: str,
    implementation_paths: list[str],
    document_paths: list[str],
) -> tuple[dict[str, Any], int]:
    findings = doctor.collect_findings(repo, full=True)
    from .paths import load_manifest
    roots = implementation_roots(repo, load_manifest(repo), [])
    facts = set(fact_documents(repo))
    all_sources = _tracked_files(repo, roots)
    if scope == "full":
        if implementation_paths or document_paths:
            add_finding(
                findings, "audit.scope", "full audit accepts no explicit paths"
            )
        sources, documents = all_sources, sorted(facts)
    else:
        if not implementation_paths and not document_paths:
            add_finding(
                findings, "audit.scope", "paths audit requires explicit paths"
            )
        sources, documents = _scope_paths(
            repo,
            implementation_paths,
            document_paths,
            roots,
            facts,
            findings,
        )
    ignored = _ignored_paths(repo, all_sources, roots, findings)
    mappings: list[dict[str, Any]] = []
    covered: set[Path] = set()
    for document in documents:
        try:
            metadata, _ = read_frontmatter(document)
        except MDFError:
            evidence: list[str] = []
        else:
            evidence = [path for path, _ in frontmatter_evidence(metadata)]
        resolved = []
        for raw in evidence:
            candidate = (repo / raw).resolve()
            if candidate in sources:
                covered.add(candidate)
            resolved.append(raw)
        mappings.append(
            {"document": relative(repo, document), "evidence": resolved}
        )
    warnings = [
        Finding(
            "audit.uncovered", "implementation file has no fact evidence",
            relative(repo, path), "warning",
        )
        for path in sources if path not in covered and path not in ignored
    ]
    payload = {
        "ok": not findings,
        "operation": "audit",
        "scope": scope,
        "repo": str(repo),
        "implementation_paths": [relative(repo, path) for path in sources],
        "document_paths": [relative(repo, path) for path in documents],
        "mappings": mappings,
        "ignored": [
            {
                "path": relative(repo, path),
                "ignore_path": rule["path"],
                "reason": rule["reason"],
            }
            for path, rule in sorted(ignored.items()) if path in sources
        ],
        "warning_count": len(warnings),
        "warnings": serialize_findings(warnings),
        "finding_count": len(findings),
        "findings": serialize_findings(findings),
    }
    return payload, 0 if not findings else 2


def command_audit(args: argparse.Namespace) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    payload, exit_code = audit_payload(
        repo,
        args.scope,
        list(args.implementation_path),
        list(args.document_path),
    )
    emit(payload)
    if exit_code:
        raise SystemExit(exit_code)
