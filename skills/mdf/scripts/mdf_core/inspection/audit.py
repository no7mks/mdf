import argparse
from functools import partial
from pathlib import Path
from typing import Any

from mdf_core.inspection import doctor
from mdf_core.inspection.code_size import is_source
from mdf_core.inspection.doc_size import sizable_documents, size_findings, size_role, structure_findings
from mdf_core.foundation.errors import Finding, MDFError, add_finding, emit, serialize_findings
from mdf_core.workspace.gitutil import git_path_tracked, repo_path, require_git_root, run
from mdf_core.inspection.overview_modules import overview_core_module_findings, project_entry_link_findings
from mdf_core.foundation.paths import path_stays_in_repo, relative
from mdf_core.foundation.progress import progress, report_progress
from mdf_core.execution.modules import MODULES_PATH, ModulesConfig, load_modules, match
from mdf_core.inspection.validate_evidence import fact_documents, frontmatter_evidence
from mdf_core.inspection.validate_manifest import implementation_roots
from mdf_core.inspection.parallel import collect_parallel
from mdf_core.foundation.yamlutil import read_frontmatter

# 不承载行为的被跟踪实现文件：版本钉、锁文件与本地配置。
# 它们不产生 audit.uncovered warning，也无需写入 evidence 或 ignorelist。
NON_BEHAVIORAL_NAMES = {
    ".gitattributes",
    ".gitignore",
    ".node-version",
    ".nvmrc",
    ".python-version",
    ".tool-versions",
    "Cargo.lock",
    "Gemfile.lock",
    "Pipfile.lock",
    "composer.lock",
    "go.sum",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "rust-toolchain.toml",
    "uv.lock",
    "yarn.lock",
}


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
            and (any(root in path.parents for root in roots) or is_source(path))
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


def _resolve_base(repo: Path, base: str | None, findings: list[Finding]) -> str | None:
    if base is None:
        result = run(["git", "merge-base", "develop", "HEAD"], cwd=repo, check=False)
        if result.returncode:
            add_finding(
                findings, "audit.base",
                "branch audit needs --base or a local develop branch",
            )
            return None
        return result.stdout.strip()
    result = run(
        ["git", "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"],
        cwd=repo, check=False,
    )
    if result.returncode:
        add_finding(findings, "audit.base", "branch audit base is not a commit", base)
        return None
    return result.stdout.strip()


def _changed_paths(repo: Path, base: str) -> list[Path]:
    """base 到当前工作区（含未提交）的改动路径。"""
    result = run(["git", "diff", "--name-only", "-z", base, "--"], cwd=repo)
    return sorted(
        {
            (repo / raw).resolve()
            for raw in result.stdout.split("\0")
            if raw and path_stays_in_repo(repo, (repo / raw).resolve())
        }
    )


def _branch_scope(
    repo: Path,
    all_sources: list[Path],
    facts: set[Path],
    changed: list[Path],
) -> tuple[list[Path], list[Path]]:
    """实现范围是改动到的实现文件；文档范围是改动到的事实页及 evidence 引用这些实现的事实页。"""
    implementation = [path for path in changed if path in set(all_sources)]
    documents = {path for path in changed if path in facts}
    touched = set(implementation)
    for document in facts:
        try:
            metadata, _ = read_frontmatter(document)
        except MDFError:
            continue
        for raw in frontmatter_evidence(metadata):
            if (repo / raw).resolve() in touched:
                documents.add(document)
                break
    return implementation, sorted(documents)


def _ignored_paths(
    repo: Path, sources: list[Path], findings: list[Finding], config: ModulesConfig
) -> tuple[dict[Path, dict[str, str]], set[str]]:
    """返回命中记录与完整 pattern 集，删除路径仍按全部规则判定范围。"""
    from mdf_core.execution.modules import match as _match

    result: dict[Path, dict[str, str]] = {}
    agents = (repo / "AGENTS.md").resolve()
    for module in config.modules.values():
        for rule in module.ignore:
            matched = [
                item
                for item in sources
                if _match(relative(repo, item), rule.pattern)
            ]
            if rule.pattern.replace("\\", "/") in {"AGENTS.md"}:
                if agents.is_file() and not agents.is_symlink():
                    result[agents] = {
                        "path": rule.pattern,
                        "reason": rule.reason,
                        "module": module.name,
                    }
                continue
            if not matched:
                add_finding(
                    findings,
                    "audit.ignore_empty",
                    "ignore pattern matches no tracked repository file",
                    f"{module.name}:{rule.pattern}",
                )
                continue
            for item in matched:
                result[item] = {
                    "path": rule.pattern,
                    "reason": rule.reason,
                    "module": module.name,
                }
    return result, {rule.pattern for _, rule in config.all_ignore_rules()}


def audit_payload(
    repo: Path,
    scope: str,
    implementation_paths: list[str],
    document_paths: list[str],
    base: str | None = None,
) -> tuple[dict[str, Any], int]:
    with progress("fact-audit 1/4：全量契约校验"):
        findings = doctor.collect_findings(repo, full=True)
    with progress("fact-audit 2/4：解析范围"):
        from mdf_core.foundation.paths import load_manifest
        roots = implementation_roots(repo, load_manifest(repo), [])
        facts = set(fact_documents(repo))
        all_tracked = _tracked_files(repo, [repo])
        all_sources = [path for path in all_tracked
                       if any(path == root or root in path.parents for root in roots)]
        try:
            size_config = load_modules(repo)
        except MDFError as exc:
            add_finding(findings, "modules.invalid", str(exc), MODULES_PATH)
            size_config = ModulesConfig()
        ignored, ignored_patterns = _ignored_paths(repo, all_tracked, findings, size_config)
        resolved_base: str | None = None
        sized: list[Path]
        if scope == "full":
            if implementation_paths or document_paths or base is not None:
                add_finding(
                    findings, "audit.scope", "full audit accepts no explicit paths"
                )
            sources, documents = all_sources, sorted(facts)
            sized = sizable_documents(repo)
            code_paths = all_tracked
        elif scope == "branch":
            if implementation_paths or document_paths:
                add_finding(
                    findings, "audit.scope", "branch audit accepts no explicit paths"
                )
            resolved_base = _resolve_base(repo, base, findings)
            changed = _changed_paths(repo, resolved_base) if resolved_base else []
            code_paths = [path for path in changed if git_path_tracked(repo, path)]
            sources, documents = _branch_scope(repo, all_sources, facts, changed)
            sized = documents + [
                path for path in changed
                if path not in facts and size_role(relative(repo, path)) is not None
            ]
        else:
            if not implementation_paths and not document_paths:
                add_finding(
                    findings, "audit.scope", "paths audit requires explicit paths"
                )
            if base is not None:
                add_finding(findings, "audit.scope", "--base only applies to branch scope")
            sources, documents = _scope_paths(
                repo,
                implementation_paths,
                document_paths,
                roots,
                facts,
                findings,
            )
            sized = documents
            code_paths = sources
    report_progress(
        "fact-audit 范围",
        f"scope={scope}，实现 {len(sources)} 份，文档 {len(documents)} 份",
    )
    with progress("fact-audit 3/4：检查文档结构"):
        limited_documents = [path for path in sized if path not in ignored]
        findings.extend(collect_parallel([
            ("文档体积", partial(size_findings, repo, limited_documents)),
            ("文档结构", partial(structure_findings, repo, limited_documents)),
            ("核心模块表", partial(overview_core_module_findings, repo, documents)),
            ("项目入口", partial(project_entry_link_findings, repo, sized)),
        ]))
    with progress("fact-audit 4/4：映射 evidence 与覆盖"):
        mappings: list[dict[str, Any]] = []
        covered: set[Path] = set()
        for document in documents:
            try:
                metadata, _ = read_frontmatter(document)
            except MDFError:
                evidence: list[str] = []
            else:
                evidence = frontmatter_evidence(metadata)
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
            for path in sources
            if path not in covered
            and path not in ignored
            and path.name not in NON_BEHAVIORAL_NAMES
        ]
    checked_paths = set(sources + code_paths + sized)
    payload = {
        "ok": not findings,
        "operation": "audit",
        "scope": scope,
        "base": resolved_base,
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
            for path, rule in sorted(ignored.items())
            if path in checked_paths or relative(repo, path) == "AGENTS.md"
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
        args.base,
    )
    emit(payload)
    if exit_code:
        raise SystemExit(exit_code)
