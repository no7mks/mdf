"""检查 profile、范围解析及独立 verdict。"""

import posixpath
from contextlib import nullcontext
from functools import partial
from pathlib import Path

from mdf_core.execution.modules import ModulesConfig, load_modules
from mdf_core.foundation.errors import Finding, MDFError, emit, serialize_findings
from mdf_core.foundation.paths import is_local_artifact_root, manifest_path, path_stays_in_repo
from mdf_core.foundation.progress import ProgressPlan, progress, report_count
from mdf_core.inspection.doc_size import size_findings, size_role, sizable_documents, structure_findings
from mdf_core.inspection.impact import contract_findings, link_findings
from mdf_core.inspection.overview_modules import overview_core_module_findings, project_entry_link_findings
from mdf_core.inspection.parallel import collect_parallel
from mdf_core.inspection.scan_context import RepoScanContext
from mdf_core.inspection.strict_validation import collect_uninitialized_findings, validate_control
from mdf_core.inspection.validate_evidence import frontmatter_evidence, validate_evidence
from mdf_core.workspace.gitutil import (
    branch_details, current_branch, git_is_clean, git_root, repo_path, require_git_root, run,
)

GROUPS = ("contract", "links", "size", "prose", "overview", "evidence", "freshness", "coverage")
PROFILES = {
    "entry": {"contract"},
    "objects": {"contract", "links", "evidence"},
    "dev": set(GROUPS) - {"freshness"},
    "closeout": set(GROUPS),
}
NON_BEHAVIORAL_NAMES = {
    ".gitattributes", ".gitignore", ".node-version", ".nvmrc", ".python-version", ".tool-versions",
    "Cargo.lock", "Gemfile.lock", "Pipfile.lock", "composer.lock", "go.sum",
    "package-lock.json", "pnpm-lock.yaml", "poetry.lock", "rust-toolchain.toml", "uv.lock", "yarn.lock",
}


def _warnings(scan, sources, documents):
    covered = set()
    mappings = []
    for document in sorted(documents):
        try:
            metadata = scan.frontmatter(document)[0]
        except (MDFError, UnicodeError):
            metadata = {}
        evidence = frontmatter_evidence(metadata)
        mappings.append({"document": scan.name(document), "evidence": evidence})
        refs = {posixpath.normpath(ref) for ref in evidence}
        covered.update(path for path in sources if any(
            ref == "." or scan.name(path) == ref or scan.name(path).startswith(ref + "/") for ref in refs
        ))
    warnings = [Finding("audit.uncovered", "implementation file has no fact evidence", scan.name(path), "warning")
                for path in sorted(set(sources) - covered) if path.name not in NON_BEHAVIORAL_NAMES]
    return mappings, warnings


def inspect_scope(scan, groups, changes, documents, sized, sources, previous, *,
                  full=False, global_objects=False, plan=None, require_history=True,
                  ignore_modules=None, ignore_paths=None):
    """check 与 fact-audit 在各自工作树上复用相同规则。"""
    repo = scan.repo
    findings = []
    with plan.stage(2) if plan else nullcontext():
        if "contract" in groups:
            try:
                config = ignore_modules if ignore_modules is not None else load_modules(repo)
            except MDFError:
                config = ModulesConfig()
            rules = list(config.all_ignore_rules())
            paths = ignore_paths
            if rules and paths is None:
                paths = scan.ignore_validation_paths
            for owner, rule in rules:
                if not any(config.ignore_matches(path, owner, rule) for path in paths):
                    findings.append(Finding("audit.ignore_empty", "ignore pattern matches no tracked file in its scope",
                                            f"{owner or 'repo'}:{rule.pattern}"))
            report_count("契约检查", 0, 1)
            with progress("契约：配置、布局、对象与记录"):
                findings.extend(contract_findings(scan, changes, documents, previous,
                                                  global_objects=global_objects, full=full))
        if "links" in groups:
            findings.extend(link_findings(scan, changes | set(sized), sized, full=full))
        if "evidence" in groups:
            shallow = require_history and "freshness" in groups and is_shallow(repo)
            if shallow:
                findings.append(Finding("audit.shallow", "需要完整 Git history 才能判断 freshness"))
            with progress("契约：事实文档与 evidence"):
                validate_evidence(repo, findings, check_staleness="freshness" in groups and not shallow,
                                  documents=sorted(documents), scan=scan)
        if "contract" in groups:
            report_count("契约检查", 1, 1)
    with plan.stage(3) if plan else nullcontext():
        checks = [
            ("size", "文档体积", partial(size_findings, repo, sized)),
            ("prose", "文档结构", partial(structure_findings, repo, sized, explicit=True)),
            ("overview", "核心模块表", partial(overview_core_module_findings, repo, sorted(documents))),
            ("overview", "项目入口", partial(project_entry_link_findings, repo, sorted(sized))),
        ]
        findings.extend(collect_parallel(
            [(label, check) for group, label, check in checks if group in groups], label="文档结构检查",
        ))
    with plan.stage(4) if plan else nullcontext():
        mappings, warnings = _warnings(scan, sources, documents) if "coverage" in groups else ([], [])
    return findings, mappings, warnings


def is_shallow(repo):
    return run(["git", "rev-parse", "--is-shallow-repository"], cwd=repo).stdout.strip() == "true"


def _disposition(item):
    return "advisory" if item.severity == "warning" else "blocking"


def _payload(metadata, findings, groups, profile, scope):
    if any(item.code == "audit.shallow" for item in findings):
        groups = groups - {"freshness"}
    values = serialize_findings(findings)
    for value, item in zip(values, findings):
        value["disposition"] = _disposition(item)
    blocking = any(value["disposition"] == "blocking" for value in values)
    ok = profile == "entry" or not blocking
    metadata["normal_workflows_allowed"] = (
        metadata["is_git_root"] and metadata["state"] == "ready" and not blocking
    )
    return {
        **metadata, "ok": ok, "operation": "check", "profile": profile, "scope": scope,
        "executed_checks": [group for group in GROUPS if group in groups],
        "skipped_checks": [group for group in GROUPS if group not in groups],
        "finding_count": len(values), "findings": values,
    }, 0 if ok else 2


def _repo_metadata(repo, findings):
    root = git_root(repo)
    branch = None
    branch_error = None
    initialized = manifest_path(repo).is_file()
    state = None
    if initialized:
        from mdf_core.foundation.paths import load_manifest
        try:
            state = load_manifest(repo).get("state")
        except MDFError:
            state = "invalid"
    if root == repo:
        try:
            branch = branch_details(current_branch(repo))
        except MDFError as exc:
            branch_error = str(exc)
            findings.append(Finding("branch.invalid", branch_error))
    return {
        "repo": str(repo), "git_root": str(root) if root else None, "is_git_root": root == repo,
        "initialized": initialized, "state": state, "branch": branch, "branch_error": branch_error,
        "clean": git_is_clean(repo) if root == repo else None,
    }


def _explicit_paths(scan, paths, *, implementation=False, config=None):
    selected = set()
    for raw in paths:
        path = scan.repo / posixpath.normpath(raw)
        valid = bool(raw) and not Path(raw).is_absolute() and path_stays_in_repo(scan.repo, path)
        if valid and scan.safe_file(path):
            rel = scan.name(path)
            valid = (rel in scan.tracked and config.owns(rel) if implementation
                     else rel in scan.visible and path.suffix == ".md" and rel != "docs/JOTS.md")
        else:
            valid = False
        if not valid:
            raise MDFError(f"无效的检查路径：{raw}", code="invalid_arguments")
        selected.add(path)
    return selected


def check_payload(repo, profile="dev", scope=None, *, base=None, against=None,
                  implementation_paths=(), document_paths=(), only=None):
    groups = PROFILES[profile].copy()
    metadata_findings = []
    metadata = _repo_metadata(repo, metadata_findings)
    if profile == "entry":
        findings = metadata_findings
        plan = ProgressPlan("check", ("检查控制面",), groups=("契约检查", "事实文档"))
        with plan.stage(1):
            if metadata["initialized"]:
                scan = RepoScanContext(repo) if metadata["is_git_root"] else None
                validate_control(repo, findings, scan=scan)
            else:
                findings.extend(collect_uninitialized_findings(repo))
        return _payload(metadata, findings, groups, profile, None)

    metadata_findings.clear()
    if not metadata["initialized"] and (only is None or "contract" in only):
        findings = metadata_findings + collect_uninitialized_findings(repo)
        findings.append(Finding("manifest.missing", "Missing MDF manifest", ".mdf/manifest.yaml"))
        return _payload(metadata, findings, {"contract"}, profile, scope)

    if only is not None:
        groups &= only
        if "evidence" not in groups:
            groups.discard("freshness")
        groups.discard("coverage")
    scope = scope or ("full" if profile == "objects" else "branch")
    if profile == "objects" and scope == "paths":
        groups.add("prose")

    from mdf_core.inspection.audit import _resolve_base
    resolved = _resolve_base(repo, against if against is not None else base, metadata_findings) if scope == "branch" else None
    if scope == "branch" and resolved is None:
        return _payload(metadata, metadata_findings, set(), profile, scope)

    scan = RepoScanContext(repo, resolved)
    try:
        config = load_modules(repo)
    except MDFError:
        config = ModulesConfig()

    explicit = _explicit_paths(scan, document_paths)
    impl = _explicit_paths(scan, implementation_paths, implementation=True, config=config)
    previous = {}
    escaped = []
    if scope == "branch":
        names = scan.changed
        previous = scan.base_frontmatter(names)
        changes = set()
        for name in names:
            path = repo / name
            if not path_stays_in_repo(repo, path):
                if not is_local_artifact_root(repo, path):
                    escaped.append(Finding("path.symlink", "变更路径指向仓库外", name))
            else:
                changes.add(path)
    elif scope == "paths":
        changes = explicit | impl
    else:
        changes = set()

    if scope == "full":
        documents = scan.facts if profile != "objects" else set()
        sized = {p for p in sizable_documents(repo) if scan.name(p) in scan.visible}
        candidates = {repo / name for name in scan.visible}
    else:
        active = {scan.name(path) for path in changes if not config.is_ignored(scan.name(path))}
        documents = scan.facts & explicit if profile == "objects" else scan.affected_facts(active, previous)
        sized = documents | explicit | {p for p in changes if size_role(scan.name(p)) and scan.safe_file(p)}
        candidates = changes
    ignored = {p for p in documents | sized | explicit | candidates if config.is_ignored(scan.name(p))}
    documents = documents - ignored
    sized = {p for p in sized if not config.is_ignored(scan.name(p))}
    if profile == "objects":
        sized = {p for p in explicit if scan.name(p).startswith(("docs/proposals/", "docs/bugs/"))
                 and not config.is_ignored(scan.name(p))}
    sources = {p for p in candidates if config.owns(scan.name(p)) and not size_role(scan.name(p))
               and not config.is_ignored(scan.name(p)) and scan.safe_file(p)}
    findings, _, warnings = inspect_scope(
        scan, groups, changes, documents, sized, sources, previous, full=scope == "full",
        global_objects=profile in {"objects", "closeout"} or scope == "full", ignore_modules=config,
    )
    metadata.update(
        base=resolved, document_paths=sorted(scan.name(path) for path in documents),
        implementation_paths=sorted(scan.name(path) for path in sources),
        ignored=sorted(scan.name(path) for path in ignored),
    )
    return _payload(metadata, metadata_findings + escaped + findings + warnings, groups, profile, scope)


def command_check(args):
    profile, scope = args.profile, args.scope
    explicit = args.document_path or args.implementation_path
    against = args.against
    only = set(args.only.split(",")) if args.only is not None else None
    invalid = (
        (profile == "entry" and scope is not None)
        or (profile in {"entry", "objects"} and (args.base is not None or against is not None or args.implementation_path))
        or (profile == "objects" and scope == "branch")
        or (against is not None and (not against or scope is not None or args.base is not None or explicit))
        or (args.base is not None and scope not in {None, "branch"})
        or (bool(explicit) != (scope == "paths"))
        or (only is not None and (profile != "dev" or not only <= set(GROUPS[:6])))
    )
    if invalid:
        raise MDFError("check 的 profile、scope、base、against、paths 或 only 组合无效", code="invalid_arguments")
    repo = repo_path(args.repo)
    if profile != "entry":
        require_git_root(repo)
    payload, code = check_payload(repo, profile, scope, base=args.base, against=against,
                                  implementation_paths=args.implementation_path,
                                  document_paths=args.document_path, only=only)
    emit(payload)
    if code:
        raise SystemExit(code)
