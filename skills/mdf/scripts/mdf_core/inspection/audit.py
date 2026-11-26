import argparse
from pathlib import Path
from typing import Any

from mdf_core.inspection.audit_quick import affected_documents, quick_exit_code
from mdf_core.inspection.code_size import is_source
from mdf_core.inspection.doc_size import sizable_documents, size_role
from mdf_core.inspection.check_engine import GROUPS, inspect_scope, is_shallow
from mdf_core.inspection.scan_context import RepoScanContext
from mdf_core.foundation.errors import Finding, MDFError, add_finding, emit, has_errors, serialize_findings
from mdf_core.workspace.gitutil import git_path_tracked, repo_path, require_git_root, run
from mdf_core.foundation.paths import path_stays_in_repo, relative
from mdf_core.foundation.progress import ProgressPlan, report_progress
from mdf_core.execution.modules import MODULES_PATH, ModulesConfig, load_modules, match
from mdf_core.inspection.validate_evidence import frontmatter_evidence
from mdf_core.inspection.validate_manifest import implementation_roots
from mdf_core.foundation.yamlutil import read_frontmatter

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
    modules: ModulesConfig,
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
            and (any(root in path.parents for root in roots) or is_source(path) or modules.owns(relative(repo, path)))
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
        from mdf_core.lifecycle.adhoc_context import context as adhoc_context
        from mdf_core.workspace.gitutil import branch_details
        from mdf_core.lifecycle.delivery_state import locate
        from mdf_core.lifecycle.roster import parse_role_branch
        from mdf_core.workspace.merge_policy import git, manifest_at
        from mdf_core.workspace.workflow_policy import integration_branch, trunk_branch
        branch = run(["git", "branch", "--show-current"], cwd=repo, check=False).stdout.strip()
        role = parse_role_branch(branch)
        owner = role[0] if role else branch
        trunk = trunk_branch(repo)
        details = branch_details(owner, trunk)
        if details["kind"] == "release":
            previous = manifest_at(repo, trunk_branch(repo)).get("versioning", {}).get("latest_release")
            if previous is None:
                add_finding(findings, "audit.base", "首次 release 需要显式 --base")
                return None
            base = f"refs/tags/v{previous}"
        elif details["supported"]:
            try:
                _, data = locate(repo)
            except MDFError:
                start = git(repo, "config", "--local", "--get", f"branch.{owner}.mdf-start-commit", check=False)
                base = start.stdout.strip() or None
                if base is None and branch == owner and branch_details(owner)["kind"] == "adhoc":
                    try:
                        base = adhoc_context(repo, owner)["range"]["base"]
                    except MDFError as exc:
                        add_finding(findings, "audit.base", str(exc))
                        return None
            else:
                base = data["start_commit"]
    if base is None:
        from mdf_core.workspace.workflow_policy import integration_branch
        result = run(["git", "merge-base", integration_branch(repo), "HEAD"], cwd=repo, check=False)
        if result.returncode:
            add_finding(
                findings, "audit.base",
                "branch audit needs --base or a local integration branch",
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


def _default_base_matches(repo, left):
    try:
        return _resolve_base(repo, None, []) == left
    except MDFError:
        return False


def _changed_paths(repo: Path, base: str) -> list[Path]:
    """base 到当前工作区（含未提交）的改动路径；rename 保留新旧两端。"""
    result = run(
        ["git", "diff", "--name-only", "--no-renames", "--ignore-submodules=none", "-z", base, "--"], cwd=repo,
    )
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
    source_set = set(all_sources)
    implementation = [path for path in changed if path in source_set]
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
    repo: Path, sources: list[Path], findings: list[Finding], config: ModulesConfig,
    *, validation_paths: list[str] | None = None,
) -> tuple[dict[Path, dict[str, str]], set[str]]:
    """返回命中记录与完整 pattern 集，删除路径仍按全部规则判定范围。"""
    result: dict[Path, dict[str, str]] = {}
    for owner, rule in config.all_ignore_rules():
        matched = [item for item in sources
                   if config.ignore_matches(relative(repo, item), owner, rule)]
        valid = bool(matched) if validation_paths is None else any(
            config.ignore_matches(path, owner, rule) for path in validation_paths
        )
        if not valid:
            add_finding(findings, "audit.ignore_empty",
                        "ignore pattern matches no tracked file in its scope",
                        f"{owner or 'repo'}:{rule.pattern}")
            continue
        for item in matched:
            if config.is_ignored(relative(repo, item)):
                result.setdefault(item, {"path": rule.pattern, "reason": rule.reason, "module": owner})
    return result, {rule.pattern for _, rule in config.all_ignore_rules()}


def audit_payload(
    repo: Path,
    scope: str,
    implementation_paths: list[str],
    document_paths: list[str],
    base: str | None = None,
    *,
    extra_documents: list[str] = (),
    ignore_modules: ModulesConfig | None = None,
    ignore_paths: list[str] | None = None,
    scope_changes: list[str] | None = None,
    global_objects: bool = True,
    original_tracked: set[str] | None = None,
) -> tuple[dict[str, Any], int]:
    plan = ProgressPlan("fact-audit", ("解析范围", "检查契约", "检查文档结构", "映射 evidence 与覆盖"),
                        groups=("契约检查", "事实文档", "文档结构检查"))
    findings: list[Finding] = []
    scan = RepoScanContext(repo, original_tracked=original_tracked)
    with plan.stage(1):
        from mdf_core.foundation.paths import load_manifest
        roots = implementation_roots(repo, load_manifest(repo), [])
        facts = scan.facts
        all_tracked = _tracked_files(repo, [repo])
        try:
            size_config = ignore_modules if ignore_modules is not None else load_modules(repo)
        except MDFError as exc:
            add_finding(findings, "modules.invalid", str(exc), MODULES_PATH)
            size_config = ModulesConfig()
        ignored, ignored_patterns = _ignored_paths(repo, all_tracked, findings, size_config,
                                                  validation_paths=ignore_paths)
        all_sources = [path for path in all_tracked if size_config.owns(relative(repo, path))
                       and size_role(relative(repo, path)) is None]
        resolved_base: str | None = None
        sized: list[Path]
        if scope == "full":
            if implementation_paths or document_paths or base is not None:
                add_finding(
                    findings, "audit.scope", "full audit accepts no explicit paths"
                )
            sources, documents = all_sources, sorted(facts)
            sized = [path for path in sizable_documents(repo) if scan.contains(path)]
            code_paths = all_tracked
        elif scope == "branch":
            if implementation_paths or document_paths:
                add_finding(
                    findings, "audit.scope", "branch audit accepts no explicit paths"
                )
            resolved_base = _resolve_base(repo, base, findings)
            changed = _changed_paths(repo, resolved_base) if resolved_base else []
            if scope_changes is not None:
                changed = [repo / p for p in scope_changes]
            changed = [p for p in changed if (size_config.owns(relative(repo, p))
                       or p in facts or size_role(relative(repo, p)) is not None)]
            code_paths = [path for path in changed if git_path_tracked(repo, path)]
            sources, documents = _branch_scope(repo, all_sources, facts,
                                               [p for p in changed if p not in ignored])
            documents = sorted(set(documents) | {repo / p for p in extra_documents if repo / p in facts})
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
                size_config,
                facts,
                findings,
            )
            affected = [p for p in sources if p not in ignored and size_config.owns(relative(repo, p))]
            documents = sorted(set(documents) | affected_documents(repo, facts, affected))
            sized = documents
            code_paths = sources
        # 实现按 module 归属过滤；事实页独立检查自身的 ignore。
        checked_paths = set(sources + code_paths + sized)
        sources = [path for path in sources if path not in ignored and size_config.owns(relative(repo, path))]
        documents = [path for path in documents if path not in ignored]
        sized = [path for path in sized if path not in ignored]
        report_progress(
            "fact-audit 范围",
            f"scope={scope}，实现 {len(sources)} 份，文档 {len(documents)} 份",
        )
    scan.base = resolved_base
    if scope == "branch":
        names = scan.changed if resolved_base else set()
        if scope_changes is not None:
            names.update(scope_changes)
        changes = {repo / name for name in names if path_stays_in_repo(repo, repo / name)}
        previous = scan.base_frontmatter(names)
        extra = scan.affected_facts({name for name in names if not size_config.is_ignored(name)}, previous)
        documents = sorted(set(documents) | {p for p in extra if not size_config.is_ignored(scan.name(p))})
        sized = sorted(set(sized) | set(documents))
    else:
        changes = set(sources + sized) if scope == "paths" else set()
        previous = {}
    result, mappings, warnings = inspect_scope(
        scan, set(GROUPS), changes, documents, sized, sources, previous,
        full=scope == "full", global_objects=global_objects, plan=plan, require_history=global_objects,
    )
    findings.extend(result)
    payload = {
        "ok": not has_errors(findings),
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
    return payload, 0 if not has_errors(findings) else 2


def _branch_fact_context(repo, base, force):
    from mdf_core.lifecycle.incremental_plan import rule_paths
    from mdf_core.reviewing.context import fingerprint
    from mdf_core.reviewing.fact_context import fact_context
    from mdf_core.workspace import clear_commits
    from mdf_core.workspace.gitutil import git_is_clean
    from mdf_core.workspace.merge_policy import sha

    clear = clear_commits.load(repo, "fact_audit")
    clean, head = git_is_clean(repo), sha(repo, "HEAD")
    changed = clear_commits.changed_paths(repo, clear, head, dirty=not clean) if clear else set()
    rules_changed = bool(changed & rule_paths(repo))
    left = clear if clear and not force and not rules_changed else base
    result = fact_context(repo, left, include_index=not clean, global_objects=True)
    expected = fact_context(repo, clear, global_objects=True) if clean and clear and left != clear else result
    trusted = clean and (left == clear or (left != head and _default_base_matches(repo, left)))
    complete = trusted and all(set(expected.get(key, [])) <= set(result[key]) for key in ("paths", "document_paths"))
    if clean and clear and left != clear:
        baseline_delta = clear_commits.changed_paths(repo, left, clear)
        complete &= not baseline_delta.intersection(expected["paths"])
    same_scope = bool(clear and clean and not rules_changed
                      and (not changed or not any((expected["paths"], expected["document_paths"],
                                                   expected["audit"]["findings"], expected["audit"]["warnings"]))))
    skip = same_scope and not force and not result["audit"]["findings"] and not result["audit"]["warnings"]
    result["clear_state"] = ({"base": clear, "head": head, "complete": complete, "same_scope": same_scope}
                             if clean else None)
    result["context_sha256"] = fingerprint({k: v for k, v in result.items() if k != "context_sha256"})
    return result, clear, skip


def command_fact_record_full(args):
    """由完成整仓语义审阅的 owner 调用。"""
    from mdf_core.workspace import clear_commits
    from mdf_core.workspace.merge_policy import sha

    repo = repo_path(args.repo)
    require_git_root(repo)
    head = sha(repo, args.head)
    base = clear_commits.load(repo, "fact_audit")
    recorded = head == args.head and clear_commits.record(repo, "fact_audit", head, expected=base)
    emit({"ok": True, "operation": "fact-audit-record-full", "result": {"recorded": recorded}})


def command_audit(args: argparse.Namespace) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    if args.quick and (not args.against or args.scope is not None or args.base is not None
                       or args.document_path or args.implementation_path or args.force):
        raise MDFError("quick 仅接受 --against <commit>", code="invalid_arguments")
    if args.quick and is_shallow(repo):
        emit({'ok': False, 'mode': 'quick', 'semantic_review': False, 'findings': serialize_findings([
            Finding('audit.shallow', 'quick 需要完整 Git history，无法在 shallow checkout 判断 stale'),
        ])})
        raise SystemExit(2)
    if args.against is not None:
        if not args.against or args.scope is not None or args.base is not None or args.implementation_path or args.document_path:
            raise MDFError('against 不能混用 scope/base/paths', code='invalid_arguments')
        from mdf_core.reviewing.fact_context import fact_context
        result = fact_context(repo, args.against, global_objects=not args.quick)
        # --quick 只跳过 LLM，不换 against 工作对象。
        exit_code = quick_exit_code(result['audit']) if args.quick else 0
        emit({'ok': not exit_code, 'result': result, 'semantic_review': not args.quick,
              'mode': 'against' if not args.quick else 'quick', 'skip_audit': False})
        if exit_code:
            raise SystemExit(exit_code)
        return
    # branch 收成 against 核：resolve-base → fact_context。
    if args.scope == 'branch':
        if args.implementation_path or args.document_path:
            raise MDFError('branch audit accepts no explicit paths', code='invalid_arguments')
        findings: list[Finding] = []
        base = _resolve_base(repo, args.base, findings)
        if findings or not base:
            raise MDFError(
                findings[0].message if findings else 'branch audit 需要可解析 base',
                code=findings[0].code if findings else 'audit.base',
            )
        result, clear, skip = _branch_fact_context(repo, base, args.force)
        emit({'ok': True, 'result': result, 'semantic_review': not skip,
              'mode': 'against', 'clear_commit': clear, 'skip_audit': skip})
        return
    payload, exit_code = audit_payload(
        repo,
        args.scope or "full",
        list(args.implementation_path),
        list(args.document_path),
        args.base,
    )
    from mdf_core.foundation.paths import load_manifest
    payload["state"] = load_manifest(repo).get("state")
    emit(payload)
    if exit_code:
        raise SystemExit(exit_code)
