from pathlib import Path

from mdf_core.foundation.errors import Finding, add_finding
from mdf_core.foundation.paths import managed_symlinks
from mdf_core.foundation.progress import progress
from mdf_core.inspection.validate_changes import validate_changes
from mdf_core.inspection.validate_evidence import validate_agents_block, validate_evidence
from mdf_core.inspection.validate_jots import validate_jots
from mdf_core.inspection.validate_layout import validate_layout
from mdf_core.inspection.validate_links import validate_links
from mdf_core.inspection.validate_manifest import validate_manifest
from mdf_core.execution.modules_check import validate_modules
from mdf_core.inspection.validate_objects import iter_object_files, validate_object
from mdf_core.inspection.validate_records import validate_adrs, validate_record_references
from mdf_core.inspection.validate_release import validate_changelog, validate_release_history


def collect_uninitialized_findings(repo: Path) -> list[Finding]:
    """无 manifest 时仍检查布局，使退休目录能在分流前被看见。"""
    findings: list[Finding] = []
    with progress("检查 1/1：未初始化布局"):
        validate_layout(repo, findings)
    return findings


def collect_findings(
    repo: Path,
    *,
    full: bool,
) -> list[Finding]:
    findings: list[Finding] = []
    with progress("检查 1/5：配置、布局与 Agent 控制面"):
        for path in managed_symlinks(repo):
            add_finding(
                findings,
                "path.symlink",
                "MDF-managed paths must not be symbolic links",
                path.relative_to(repo).as_posix(),
            )
        manifest = validate_manifest(repo, findings)
        validate_modules(repo, findings)
        validate_layout(repo, findings)
        validate_agents_block(repo, findings)
    with progress("检查 2/5：Jot、Proposal 与 Bug"):
        validate_jots(repo, findings)
        for path in iter_object_files(repo, "proposal"):
            validate_object(repo, path, "proposal", findings)
        for path in iter_object_files(repo, "bug"):
            validate_object(repo, path, "bug", findings)
    with progress("检查 3/5：链接、Change 与 ADR"):
        validate_links(repo, findings)
        validate_changes(repo, findings)
        validate_adrs(repo, findings)
        validate_record_references(repo, findings)
    with progress("检查 4/5：发布历史"):
        validate_changelog(repo, findings)
        validate_release_history(repo, manifest, findings)
    with progress("检查 5/5：事实文档与 evidence"):
        validate_evidence(
            repo,
            findings,
            check_staleness=full,
        )
    if manifest and manifest.get("state") != "ready":
        add_finding(
            findings,
            "manifest.initializing",
            "manifest 未 ready 前使用 $mdf init 或 $mdf migrate；"
            "符合新仓库条件时可用 $mdf bootstrap",
            ".mdf/manifest.yaml",
        )
    return findings
