"""范围事实审阅的契约影响集；inventory 读取不等于全库校验。"""
from mdf_core.foundation.errors import MDFError, add_finding
from mdf_core.foundation.paths import relative, load_manifest
from mdf_core.foundation.yamlutil import read_frontmatter, parse_yaml
from mdf_core.foundation.progress import report_count
from mdf_core.workspace.gitutil import run
from mdf_core.inspection import doctor
from mdf_core.inspection.validate_changes import validate_changes
from mdf_core.inspection.validate_evidence import validate_evidence
from mdf_core.inspection.validate_links import managed_markdown, collect_local_link_findings
from mdf_core.inspection.validate_objects import iter_object_files, validate_object
from mdf_core.inspection.validate_records import validate_adrs, validate_record_references
from mdf_core.inspection.validate_release import validate_changelog, validate_release_history


def collect_impact_findings(repo, changes, documents, base):
    report_count("契约检查", 0, 1)
    changed = set(changes)
    findings = []
    manifest = doctor.validate_manifest(
        repo, findings, documents=None if repo / ".mdf/manifest.yaml" in changed else changed | set(documents))
    if manifest and manifest.get("state") != "ready":
        add_finding(findings, "manifest.initializing",
                    "manifest 未 ready 前使用 $mdf init 或 $mdf migrate", ".mdf/manifest.yaml")
    # 配置是范围解析的前提；变更控制面或测试布局时按对应边界检查。
    if any(relative(repo, p) == '.mdf/modules.yaml' or relative(repo, p).startswith('docs/system/testing/') for p in changed):
        doctor.validate_modules(repo, findings, paths=changed)
    if any(relative(repo, p).startswith('docs/system/testing/') for p in changed):
        doctor.validate_layout(repo, findings)
    if repo / 'AGENTS.md' in changed:
        doctor.validate_agents_block(repo, findings)
    validate_evidence(repo, findings, check_staleness=True, documents=documents)
    for path in managed_markdown(repo):
        collect_local_link_findings(repo, path, findings,
                                    targets=None if path in changed else changed, check_anchors=True)
    touched_ids = set()
    for path in changed:
        if path.suffix not in {'.md', '.html'}:
            continue
        if path.is_file():
            try:
                metadata, _ = read_frontmatter(path)
                touched_ids.update(value for key in ('id', 'milestone')
                                   if isinstance(value := metadata.get(key), str))
            except MDFError:
                pass
        if base:
            old = run(['git', 'show', f'{base}:{relative(repo, path)}'], cwd=repo, check=False)
            if old.returncode == 0 and old.stdout.startswith('---\n'):
                try:
                    metadata = parse_yaml(old.stdout.split('---', 2)[1])
                    touched_ids.update(value for key in ('id', 'milestone')
                                       if isinstance(value := metadata.get(key), str))
                except MDFError:
                    pass
    for kind in ('proposal', 'bug'):
        for path in iter_object_files(repo, kind):
            if path in changed:
                validate_object(repo, path, kind, findings)
    if repo / 'docs/JOTS.md' in changed:
        doctor.validate_jots(repo, findings)
    validate_adrs(repo, findings, paths=changed)
    validate_changes(repo, findings, paths=changed)
    validate_record_references(repo, findings, paths=changed, touched_ids=touched_ids)
    # 发布记录是 manifest / CHANGELOG / 版本 Change 的关联约束。
    release_changes = {p for p in changed if relative(repo, p) in {'.mdf/manifest.yaml', 'CHANGELOG.md'}
                       or relative(repo, p).startswith('changes/')}
    if release_changes:
        if repo / 'CHANGELOG.md' in changed:
            validate_changelog(repo, findings)
        validate_release_history(repo, load_manifest(repo), findings, paths=changed)
    report_count("契约检查", 1, 1)
    return findings
