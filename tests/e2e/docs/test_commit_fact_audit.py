"""PR 事实审阅固定 snapshot、影响映射与报告完整性（against→工作区）。"""
import copy
import json

import pytest

from mdf_test_support import copy_fixture, git, init_git, mdf, payload
from mdf_core.foundation.errors import MDFError
from mdf_core.reviewing.fact_context import fact_context
from mdf_core.reviewing.fact_report import validate_fact_report


def commit(repo):
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'test: 更新事实')
    return git(repo, 'rev-parse', 'HEAD').stdout.strip()


def repository(tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    base = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    return repo, base


def report_for(context):
    report = {k: context[k] for k in ('schema_version', 'mode', 'operation', 'against', 'worktree_sha256', 'rules_sha256', 'context_sha256', 'paths',
                                     'implementation_paths', 'document_paths')}
    report.update(findings=[], incomplete=[], warnings=[
        {'index': i, 'disposition': 'accepted', 'evidence': '内部常量，无可观察契约'}
        for i, _ in enumerate(context['audit']['warnings'])],
        decision='changes_requested' if context['audit']['findings'] else 'pass')
    return copy.deepcopy(report)


def test_against_audit_compares_worktree_without_mutation(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/service.py').write_text('updated = True\n')
    (repo / 'src/new.py').write_text('added = True\n')
    (repo / '.gitignore').write_text('src/ignored.py\n')
    (repo / 'src/ignored.py').write_text('excluded = True\n')
    commit(repo)
    files = {p.relative_to(repo): p.read_bytes() for p in repo.rglob('*') if p.is_file()}
    ctx = payload(mdf(python_exe, 'fact-audit', '--repo', str(repo), '--against', base))['result']
    assert ctx['against'] == base and ctx['mode'] == 'against'
    assert 'worktree_sha256' in ctx and 'src/new.py' in ctx['paths'] and 'src/service.py' in ctx['paths']
    assert '+updated = True' in ctx['diff'] and '+added = True' in ctx['diff']
    assert 'excluded = True' not in ctx['diff']
    assert 'docs/system/interfaces/api.md' in ctx['document_paths']
    assert files == {p.relative_to(repo): p.read_bytes() for p in repo.rglob('*') if p.is_file()}
    assert not {'review_head', 'policy_ref', 'target_paths', 'target_diff', 'roster'} & ctx.keys()


def test_against_includes_dirty_worktree(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/service.py').write_text('dirty = True\n')
    ctx = payload(mdf(python_exe, 'fact-audit', '--repo', str(repo), '--against', base))['result']
    assert ctx['against'] == base and 'src/service.py' in ctx['paths']
    assert '+dirty = True' in ctx['diff']


def test_against_checks_evidence_outside_module_sourcesets(python_exe, tmp_path):
    repo, _ = repository(tmp_path)
    evidence = repo / 'maintenance/bootstrap.py'
    evidence.parent.mkdir()
    evidence.write_text('VERSION = 1\n')
    doc_path = 'docs/system/interfaces/api.md'
    doc = repo / doc_path
    doc.write_text(doc.read_text().replace('path: src/service.py', 'path: maintenance/bootstrap.py'))
    base = commit(repo)
    evidence.write_text('VERSION = 2\n')
    commit(repo)

    result = mdf(python_exe, 'fact-audit', '--repo', str(repo), '--against', base, '--quick')
    assert result.returncode == 2
    ctx = json.loads(result.stdout)['result']
    assert ctx['document_paths'] == [doc_path]
    assert [(f['code'], f['path']) for f in ctx['audit']['findings']] == [('evidence.stale', doc_path)]
    assert ctx['implementation_paths'] == ctx['audit']['implementation_paths'] == []
    assert ctx['audit']['warnings'] == []


@pytest.mark.parametrize('change', ['delete', 'rename', 'remove-evidence', 'delete-doc'])
def test_commit_audit_keeps_base_evidence_impacts(tmp_path, change):
    repo, base = repository(tmp_path)
    service = repo / 'src/service.py'
    doc = repo / 'docs/system/interfaces/api.md'
    if change == 'delete':
        service.unlink()
    elif change == 'rename':
        service.rename(repo / 'src/renamed.py')
    elif change == 'remove-evidence':
        service.write_text('VALUE = 2\n')
        doc.write_text(doc.read_text().replace('  - path: src/service.py\n', ''))
    else:
        doc.unlink()
    commit(repo)
    ctx = fact_context(repo, base)
    assert 'docs/system/interfaces/api.md' in ctx['document_paths']
    assert ctx['base_mappings']['docs/system/interfaces/api.md'] == ['src/service.py']
    if change != 'delete-doc':
        assert 'src/service.py' in ctx['implementation_paths']
    if change == 'rename':
        assert 'src/renamed.py' in ctx['implementation_paths']


def test_source_module_ignore_excludes_new_implementation(tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/new.py').write_text('VALUE = 2\n')
    modules = repo / '.mdf/modules.yaml'
    modules.write_text(modules.read_text().replace('    ignore: []',
                      '    ignore:\n      - pattern: src/new.py\n        reason: skip'))
    commit(repo)
    ctx = fact_context(repo, base)
    assert ctx['rules']['modules'] == modules.read_text()
    assert 'src/new.py' not in ctx['paths'] and ctx['implementation_paths'] == []
    assert ctx['ignored'] == [{'path': 'src/new.py', 'ignore_path': 'src/new.py', 'reason': 'skip'}]
    assert ctx['audit']['warnings'] == []


@pytest.mark.parametrize('change', ['modify', 'delete', 'rename', 'move-out', 'move-in'])
def test_sourceset_excludes_installed_mdf_from_commit_review(python_exe, tmp_path, change):
    repo, _ = repository(tmp_path)
    installed = '.agents/skills/mdf'
    vendor = repo / installed / 'scripts/tool.py'
    vendor.parent.mkdir(parents=True)
    vendor.write_text('VALUE = 1\n')
    project = repo / 'src/tool.py'
    if change == 'move-in':
        project.write_text('VALUE = 2\n')
    target = commit(repo)
    if change == 'modify':
        vendor.write_text('VALUE = 2\n')
    elif change == 'delete':
        vendor.unlink()
    elif change == 'rename':
        vendor.rename(vendor.with_name('renamed.py'))
    elif change == 'move-out':
        vendor.rename(project)
    else:
        project.rename(vendor.with_name('new.py'))
    commit(repo)
    ctx = payload(mdf(python_exe, 'fact-audit', '--repo', str(repo),
                      '--against', target))['result']
    expected = ['src/tool.py'] if change in {'move-out', 'move-in'} else []
    assert ctx['implementation_paths'] == expected
    assert ctx['paths'] == expected
    assert ctx['document_paths'] == []
    assert ctx['ignored'] == []
    assert f'diff --git a/{installed}/' not in ctx['diff']
    context_file, report_file = tmp_path / 'context.json', tmp_path / 'report.json'
    context_file.write_text(json.dumps(ctx))
    report_file.write_text(json.dumps(report_for(ctx)))
    checked = payload(mdf(python_exe, 'fact-audit-report-check', '--repo', str(repo), '--context-file', str(context_file),
                          '--report-file', str(report_file)))
    assert checked['result']['decision'] == 'pass'


def test_vendor_ignore_keeps_project_code_and_fact_pages_in_review(python_exe, tmp_path):
    repo, _ = repository(tmp_path)
    vendor = repo / '.codex/skills/mdf/tool.py'
    vendor.parent.mkdir(parents=True)
    vendor.write_text('VALUE = 1\n')
    modules = repo / '.mdf/modules.yaml'
    modules.write_text(modules.read_text().replace(
        '    ignore: []', '      - ".codex/skills/mdf/**"\n'
        '    ignore:\n      - pattern: ".codex/skills/mdf/**"\n        reason: 排除已安装的 MDF'))
    doc = repo / 'docs/system/interfaces/api.md'
    doc.write_text(doc.read_text().replace('evidence:\n',
                   'evidence:\n  - path: .codex/skills/mdf/tool.py\n'))
    target = commit(repo)
    vendor.write_text('VALUE = 2\n')
    commit(repo)
    ctx = fact_context(repo, target)
    assert ctx['paths'] == ctx['implementation_paths'] == []
    assert ctx['document_paths'] == []
    assert [item['path'] for item in ctx['ignored']] == ['.codex/skills/mdf/tool.py']
    (repo / 'src/service.py').write_text('def healthy():\n    return True\n\n# project change\n')
    doc.write_text(doc.read_text() + '\n项目事实变更。\n')
    commit(repo)
    ctx = payload(mdf(python_exe, 'fact-audit', '--repo', str(repo),
                      '--against', target))['result']
    assert ctx['paths'] == ['docs/system/interfaces/api.md', 'src/service.py']
    assert ctx['implementation_paths'] == ['src/service.py']
    expected_documents = sorted(p for p, evidence in ctx['base_mappings'].items() if 'src/service.py' in evidence)
    assert ctx['document_paths'] == expected_documents
    assert any(f['code'] == 'evidence.stale' for f in ctx['audit']['findings'])
    report = report_for(ctx)
    assert validate_fact_report(ctx, report)['decision'] == 'changes_requested'
    report.update(document_paths=[], decision='pass')
    with pytest.raises(MDFError, match='未完成复核'):
        validate_fact_report(ctx, report)


def test_unowned_mdf_is_outside_review_even_with_unrelated_module_ignore(tmp_path):
    repo, _ = repository(tmp_path)
    vendor = repo / '.codex/skills/mdf/tool.py'
    vendor.parent.mkdir(parents=True)
    vendor.write_text('VALUE = 1\n')
    modules = repo / '.mdf/modules.yaml'
    modules.write_text(modules.read_text().replace('    ignore: []\n',
        '    ignore:\n      - pattern: "**"\n        reason: 本 module 排除\n', 1))
    target = commit(repo)
    vendor.write_text('VALUE = 2\n')
    commit(repo)
    ctx = fact_context(repo, target)
    assert ctx['paths'] == ctx['implementation_paths'] == []
    assert ctx['ignored'] == ctx['audit']['ignored'] == []


@pytest.mark.parametrize('change', ['delete', 'rename', 'target-only', 'invalid-target'])
def test_removed_source_ignore_does_not_use_target_rules(tmp_path, change):
    repo, base = repository(tmp_path)
    modules = repo / '.mdf/modules.yaml'
    original = modules.read_text()
    rule = '    ignore:\n      - pattern: src/generated.py\n        reason: generated\n'
    modules.write_text(original.replace('    ignore: []\n', rule, 1))
    if change != 'invalid-target':
        (repo / 'src/generated.py').write_text('VALUE = 1\n')
    target = commit(repo)
    if change == 'target-only':
        git(repo, 'checkout', '--detach', base)
        (repo / 'unrelated.txt').write_text('source\n')
        commit(repo)
    elif change == 'invalid-target':
        (repo / 'src/generated.py').write_text('VALUE = 1\n')
        commit(repo)
    else:
        if change == 'delete':
            (repo / 'src/generated.py').unlink()
        else:
            (repo / 'src/generated.py').rename(repo / 'src/renamed.py')
        modules.write_text(original)
        commit(repo)
    ctx = fact_context(repo, target)
    findings = ctx['audit']['findings']
    assert findings == []
    assert validate_fact_report(ctx, report_for(ctx))['decision'] == 'pass'
    if change == 'invalid-target':
        assert ctx['implementation_paths'] == []
        assert ctx['ignored'] == [{'path': 'src/generated.py', 'ignore_path': 'src/generated.py', 'reason': 'generated'}]
    elif change in {'delete', 'rename'}:
        assert 'src/generated.py' in ctx['implementation_paths'] and ctx['ignored'] == []
    if change == 'rename':
        assert any(w['path'] == 'src/renamed.py' for w in ctx['audit']['warnings'])


@pytest.mark.parametrize('object_format,host_default', [('sha256', 'sha1'), ('sha1', 'sha256')])
def test_commit_audit_inherits_object_format(tmp_path, monkeypatch, object_format, host_default):
    repo = copy_fixture(tmp_path)
    git(repo, 'init', '--object-format=' + object_format)
    init_git(repo)
    target = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    (repo / 'src/new.py').write_text('VALUE = 1\n')
    commit(repo)
    monkeypatch.setenv('GIT_DEFAULT_HASH', host_default)
    ctx = fact_context(repo, target)
    assert ctx['against'] == target
    assert ctx['paths'] == ['src/new.py']
    assert ctx['audit']['findings'] == []
    assert validate_fact_report(ctx, report_for(ctx))['decision'] == 'pass'


def test_deleted_evidence_matches_normalized_relative_paths(tmp_path):
    repo, _ = repository(tmp_path)
    doc = repo / 'docs/system/interfaces/api.md'
    doc.write_text(doc.read_text().replace('path: src/service.py', 'path: ./src/service.py'))
    base = commit(repo)
    (repo / 'src/service.py').unlink()
    commit(repo)
    ctx = fact_context(repo, base)
    assert 'docs/system/interfaces/api.md' in ctx['document_paths']
    assert 'docs/system/interfaces/api.md' in ctx['audit']['document_paths']


@pytest.mark.parametrize('dependency', ['directory', 'generated-source', 'generator'])
def test_indirect_fact_dependencies_are_in_review_scope(tmp_path, dependency):
    repo, _ = repository(tmp_path)
    doc = repo / 'docs/system/interfaces/api.md'
    if dependency == 'directory':
        doc.write_text(doc.read_text().replace('path: src/service.py', 'path: src'))
        changed = repo / 'src/service.py'
    else:
        schema = repo / 'schema.yaml'
        schema.write_text('value: 1\n')
        generator = repo / 'generate.py'
        generator.write_text('#!/usr/bin/env python3\n')
        generator.chmod(0o755)
        doc.write_text(doc.read_text().replace('evidence:\n',
                       'generated:\n  source: schema.yaml\n  generator: generate.py\nevidence:\n'))
        modules = repo / '.mdf/modules.yaml'
        modules.write_text(modules.read_text().replace('"src/**"', '"src/**"\n      - "schema.yaml"\n      - "generate.py"', 1))
        changed = schema if dependency == 'generated-source' else generator
    base = commit(repo)
    changed.write_text(changed.read_text() + '\n# changed\n')
    commit(repo)
    ctx = fact_context(repo, base)
    assert 'docs/system/interfaces/api.md' in ctx['document_paths']
    assert 'docs/system/interfaces/api.md' in ctx['audit']['document_paths']


def test_shallow_snapshot_preserves_available_history(tmp_path):
    repo, _ = repository(tmp_path)
    for i in range(3):
        (repo / 'unrelated.txt').write_text(str(i))
        commit(repo)
    shallow = tmp_path / 'shallow'
    git(tmp_path, 'clone', '--depth=2', repo.as_uri(), str(shallow))
    head = git(shallow, 'rev-parse', 'HEAD').stdout.strip()
    ctx = fact_context(shallow, head)
    assert ctx['audit']['findings'] == []


@pytest.mark.parametrize('extra', [['--scope', 'full'], ['--scope', 'branch'], ['--base', 'HEAD'],
                                  ['--implementation-path', 'src/service.py']])
def test_against_audit_rejects_mixed_arguments(python_exe, tmp_path, extra):
    repo, base = repository(tmp_path)
    result = mdf(python_exe, 'fact-audit', '--repo', str(repo), '--against', base, *extra)
    assert result.returncode != 0 and 'invalid_arguments' in result.stderr


def test_against_audit_rejects_unknown_reference(tmp_path):
    repo, _ = repository(tmp_path)
    with pytest.raises(MDFError):
        fact_context(repo, 'absent-ref')


def test_snapshot_does_not_run_filters_or_follow_symlinks(tmp_path, monkeypatch):
    repo, base = repository(tmp_path)
    marker = tmp_path / 'ran-filter'
    git(repo, 'config', 'filter.hostile.smudge', f'touch {marker}')
    (repo / '.gitattributes').write_text('src/* filter=hostile export-ignore\n')
    commit(repo)
    config = tmp_path / 'global-config'
    config.write_text('[filter \"hostile\"]\n\tclean = touch ' + str(marker) + '\n')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(config))
    ctx = fact_context(repo, base)
    assert not marker.exists() and 'src/service.py' in ctx['worktree_mappings']['docs/system/interfaces/api.md']
    monkeypatch.delenv('GIT_CONFIG_GLOBAL')
    (repo / 'escape').symlink_to(tmp_path)
    git(repo, 'add', 'escape')
    commit(repo)
    with pytest.raises(MDFError, match='symlink|非普通文件|不安全路径'):
        fact_context(repo, base)
    assert not marker.exists()


def test_fact_report_cli_accepts_complete_clean_review(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    ctx = fact_context(repo, base)
    report = report_for(ctx)
    assert report['decision'] == 'pass'
    context_file, report_file = tmp_path / 'context.json', tmp_path / 'report.json'
    context_file.write_text(json.dumps(ctx))
    report_file.write_text(json.dumps(report))
    result = payload(mdf(python_exe, 'fact-audit-report-check', '--repo', str(repo), '--context-file', str(context_file),
                         '--report-file', str(report_file)))
    assert result['result']['decision'] == 'pass'


@pytest.mark.parametrize('damage', ['fingerprint', 'worktree', 'coverage', 'warning', 'semantic', 'validation', 'incomplete'])
def test_fact_report_rejects_false_pass(tmp_path, damage):
    repo, base = repository(tmp_path)
    (repo / 'src/new.py').write_text('VALUE = 1\n')
    commit(repo)
    ctx = fact_context(repo, base)
    report = report_for(ctx)
    report['decision'] = 'pass'
    if damage == 'fingerprint':
        ctx['diff'] = 'forged'
    elif damage == 'worktree':
        report['worktree_sha256'] = 'wrong'
    elif damage == 'coverage':
        report['implementation_paths'] = []
    elif damage == 'warning':
        report['warnings'] = []
    elif damage == 'semantic':
        report['findings'] = [{'id': 'f1', 'path': 'src/new.py', 'line': 1, 'priority': 3,
                               'trigger': '调用', 'impact': '事实错误', 'evidence': 'source:src/new.py:1'}]
    elif damage == 'validation':
        from mdf_core.reviewing.context import fingerprint
        ctx['audit']['findings'].append({'code': 'test', 'path': 'src/new.py'})
        ctx['context_sha256'] = fingerprint({k: v for k, v in ctx.items() if k != 'context_sha256'})
        report['context_sha256'] = ctx['context_sha256']
    else:
        report['incomplete'] = ['尚未读取事实页']
    with pytest.raises(MDFError):
        validate_fact_report(ctx, report)


def test_fact_report_allows_explicit_incomplete_and_findings(tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/service.py').unlink()
    commit(repo)
    ctx = fact_context(repo, base)
    report = report_for(ctx)
    assert validate_fact_report(ctx, report)['decision'] == 'changes_requested'
    report.update(document_paths=[], incomplete=['事实页尚未复核'], decision='needs-review')
    assert validate_fact_report(ctx, report)['decision'] == 'needs-review'


@pytest.mark.parametrize('field,value', [('audit', None), ('audit', {}), ('paths', None),
                                        ('document_paths', [{}])])
def test_fact_report_rejects_malformed_context_with_structured_error(tmp_path, field, value):
    from mdf_core.reviewing.context import fingerprint
    repo, base = repository(tmp_path)
    ctx = fact_context(repo, base)
    report = report_for(ctx)
    ctx[field] = value
    ctx['context_sha256'] = fingerprint({k: v for k, v in ctx.items() if k != 'context_sha256'})
    report['context_sha256'] = ctx['context_sha256']
    with pytest.raises(MDFError):
        validate_fact_report(ctx, report)


@pytest.mark.parametrize('roots', ['null', '[1]', '[{}]'])
def test_against_audit_reports_invalid_current_manifest(tmp_path, roots):
    repo, base = repository(tmp_path)
    manifest = repo / '.mdf/manifest.yaml'
    manifest.write_text(manifest.read_text().replace('implementation_roots: [src]', 'implementation_roots: ' + roots))
    commit(repo)
    ctx = fact_context(repo, base)
    assert ctx['audit']['findings']


@pytest.mark.parametrize('root', ['.', './src'])
def test_commit_audit_normalizes_implementation_roots(tmp_path, root):
    repo, _ = repository(tmp_path)
    manifest = repo / '.mdf/manifest.yaml'
    manifest.write_text(manifest.read_text().replace('implementation_roots: [src]', f'implementation_roots: [{root}]'))
    base = commit(repo)
    (repo / 'src/config.json').write_text('{"enabled": true}\n')
    commit(repo)
    ctx = fact_context(repo, base)
    assert 'src/config.json' in ctx['implementation_paths']
