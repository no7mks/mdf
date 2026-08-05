from pathlib import Path

from .errors import Finding, add_finding
from .paths import managed_symlinks
from .validate_changes import validate_changes
from .validate_evidence import validate_agents_block, validate_evidence
from .validate_jots import validate_jots
from .validate_links import validate_links
from .validate_manifest import validate_manifest
from .validate_objects import iter_object_files, validate_object
from .validate_records import validate_adrs, validate_record_references
from .validate_release import validate_changelog, validate_release_history


def collect_findings(
    repo: Path,
    *,
    full: bool,
) -> list[Finding]:
    findings: list[Finding] = []
    for path in managed_symlinks(repo):
        add_finding(
            findings,
            "path.symlink",
            "MDF-managed paths must not be symbolic links",
            path.relative_to(repo).as_posix(),
        )
    manifest = validate_manifest(
        repo,
        findings,
        require_verification_commands=full,
    )
    validate_agents_block(repo, findings)
    validate_jots(repo, findings)
    for path in iter_object_files(repo, "proposal"):
        validate_object(repo, path, "proposal", findings)
    for path in iter_object_files(repo, "bug"):
        validate_object(repo, path, "bug", findings)
    validate_links(repo, findings)
    validate_changes(repo, findings)
    validate_adrs(repo, findings)
    validate_record_references(repo, findings)
    validate_changelog(repo, findings)
    validate_release_history(repo, manifest, findings)
    validate_evidence(
        repo,
        findings,
        check_staleness=full,
    )
    if manifest and manifest.get("state") != "ready":
        add_finding(
            findings,
            "manifest.initializing",
            "manifest 未 ready 前只允许 $mdf init",
            ".mdf/manifest.yaml",
        )
    return findings
