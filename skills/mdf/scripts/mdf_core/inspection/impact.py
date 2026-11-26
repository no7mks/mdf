"""静态检查共享的契约规则及影响集。"""

from mdf_core.foundation.errors import MDFError
from mdf_core.inspection.strict_validation import validate_control
from mdf_core.inspection.validate_changes import validate_changes
from mdf_core.inspection.validate_jots import validate_jots
from mdf_core.inspection.validate_links import managed_markdown, collect_local_link_findings
from mdf_core.inspection.validate_objects import iter_object_files, validate_object
from mdf_core.inspection.validate_records import validate_adrs, validate_record_references
from mdf_core.inspection.validate_release import validate_changelog, validate_release_history


def contract_findings(scan, changes, documents, previous, *, global_objects=False, full=False):
    repo = scan.repo
    findings = []
    manifest = validate_control(
        repo, findings, documents=None if full or repo / ".mdf/manifest.yaml" in changes
        else changes | set(documents), scan=scan,
    )
    paths = None if global_objects else changes
    touched_ids = set()
    for path in changes:
        if path.suffix not in {".md", ".html"}:
            continue
        metadata = [previous.get(scan.name(path), {})]
        if scan.safe_file(path):
            try:
                metadata.append(scan.frontmatter(path)[0])
            except (MDFError, UnicodeError):
                pass
        touched_ids.update(value for item in metadata for key in ("id", "milestone")
                           if isinstance(value := item.get(key), str))
    for kind in ("proposal", "bug"):
        for path in iter_object_files(repo, kind):
            if (paths is None or path in paths) and scan.name(path) in scan.visible:
                validate_object(repo, path, kind, findings)
    if paths is None or repo / "docs/JOTS.md" in paths:
        validate_jots(repo, findings, scan=scan)
    validate_adrs(repo, findings, paths=paths, scan=scan)
    validate_changes(repo, findings, paths=paths, scan=scan)
    validate_record_references(repo, findings, paths=paths, touched_ids=touched_ids, scan=scan)

    release_changes = any(scan.name(path) in {".mdf/manifest.yaml", "CHANGELOG.md"}
                          or scan.name(path).startswith("changes/") for path in changes)
    if paths is None or release_changes:
        if paths is None or repo / "CHANGELOG.md" in paths:
            validate_changelog(repo, findings, scan=scan)
        if manifest is not None:
            validate_release_history(repo, manifest, findings, paths=paths, scan=scan)
    return findings


def link_findings(scan, changes, documents, *, full=False):
    repo = scan.repo
    findings = []
    sources = set(managed_markdown(repo)) | set(documents)
    sources.update(path for path in changes if path.suffix == ".md" and path.is_file())
    sources.update(repo / raw for raw in ("README.md", "AGENTS.md") if scan.safe_file(repo / raw))
    targets = {path.resolve() for path in changes}
    for path in sorted(sources):
        if scan.name(path) in scan.visible and scan.safe_file(path):
            collect_local_link_findings(repo, path, findings,
                                        targets=None if full or path in changes else targets,
                                        check_anchors=True, scan=scan)
    return findings
