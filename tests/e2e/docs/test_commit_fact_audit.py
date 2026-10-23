"""PR 事实审阅固定 snapshot、影响映射与报告完整性。"""
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
    report = {k: context[k] for k in ('schema_version', 'mode', 'operation', 'review_base', 'review_head',
                                     'policy_ref', 'rules_sha256', 'context_sha256', 'paths',
                                     'implementation_paths', 'document_paths')}
    report.update(findings=[], incomplete=[], warnings=[
        {'index': i, 'disposition': 'accepted', 'evidence': '内部常量，无可观察契约'}
        for i, _ in enumerate(context['audit']['warnings'])],
        decision='changes_requested' if context['audit']['findings'] else 'pass')
    return copy.deepcopy(report)


def test_commit_audit_uses_source_snapshot_and_keeps_checkout_untouched(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/service.py').write_text('def healthy():\n    return False\n')
    source = commit(repo)
    git(repo, 'checkout', '--detach', base)
    (repo / 'target-only.txt').write_text('target\n')
    target = commit(repo)
    (repo / 'src/service.py').write_text('dirty = True\n')
    before = git(repo, 'status', '--porcelain=v1').stdout
    index = (repo / '.git/index').read_bytes()
    files = {p.relative_to(repo): p.read_bytes() for p in repo.rglob('*') if p.is_file()}
    ctx = payload(mdf(python_exe, 'fact-audit', '--repo', str(repo),
                      '--source-commit', source, '--target-commit', target))['result']
    assert ctx['review_base'] == base and ctx['review_head'] == source
    assert ctx['paths'] == ['src/service.py']
    assert ctx['target_paths'] == ['target-only.txt']
    assert 'dirty' not in ctx['diff'] and '+    return False' in ctx['diff']
    assert 'docs/system/interfaces/api.md' in ctx['document_paths']
    assert any(f['code'].startswith('evidence.') for f in ctx['audit']['findings'])
    assert git(repo, 'status', '--porcelain=v1').stdout == before
    assert git(repo, 'rev-parse', 'HEAD').stdout.strip() == target
    assert (repo / '.git/index').read_bytes() == index
    assert files == {p.relative_to(repo): p.read_bytes() for p in repo.rglob('*') if p.is_file()}
    assert not (repo / 'audit-ran').exists()
    assert not {'roster', 'artifacts', 'delivery_base'} & ctx.keys()


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
    source = commit(repo)
    ctx = fact_context(repo, source, base)
    assert 'docs/system/interfaces/api.md' in ctx['document_paths']
    assert ctx['base_mappings']['docs/system/interfaces/api.md'] == ['src/service.py']
    if change != 'delete-doc':
        assert 'src/service.py' in ctx['implementation_paths']
    if change == 'rename':
        assert 'src/renamed.py' in ctx['implementation_paths']


def test_source_ignore_cannot_hide_new_implementation(tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/new.py').write_text('VALUE = 2\n')
    modules = repo / '.mdf/modules.yaml'
    modules.write_text(modules.read_text().replace('    ignore: []',
                      '    ignore:\n      - pattern: src/new.py\n        reason: skip'))
    ctx = fact_context(repo, commit(repo), base)
    assert ctx['rules']['modules'] == git(repo, 'show', base + ':.mdf/modules.yaml').stdout
    assert any(w['path'] == 'src/new.py' for w in ctx['audit']['warnings'])


@pytest.mark.parametrize('change', ['delete', 'rename', 'target-only', 'invalid-target'])
def test_ignore_policy_is_validated_against_target(tmp_path, change):
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
    elif change == 'invalid-target':
        (repo / 'src/generated.py').write_text('VALUE = 1\n')
    else:
        if change == 'delete':
            (repo / 'src/generated.py').unlink()
        else:
            (repo / 'src/generated.py').rename(repo / 'src/renamed.py')
        modules.write_text(original)
    ctx = fact_context(repo, commit(repo), target)
    findings = ctx['audit']['findings']
    if change == 'invalid-target':
        assert any(f['code'] == 'audit.ignore_empty' for f in findings)
    else:
        assert findings == []
        assert validate_fact_report(ctx, report_for(ctx))['decision'] == 'pass'
    if change == 'rename':
        assert any(w['path'] == 'src/renamed.py' for w in ctx['audit']['warnings'])


@pytest.mark.parametrize('object_format,host_default', [('sha256', 'sha1'), ('sha1', 'sha256')])
def test_commit_audit_inherits_object_format(tmp_path, monkeypatch, object_format, host_default):
    repo = copy_fixture(tmp_path)
    git(repo, 'init', '--object-format=' + object_format)
    init_git(repo)
    target = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    (repo / 'src/new.py').write_text('VALUE = 1\n')
    source = commit(repo)
    monkeypatch.setenv('GIT_DEFAULT_HASH', host_default)
    ctx = fact_context(repo, source, target)
    assert ctx['review_head'] == source and ctx['review_base'] == target
    assert ctx['paths'] == ['src/new.py']
    assert ctx['audit']['findings'] == []
    assert validate_fact_report(ctx, report_for(ctx))['decision'] == 'pass'


def test_deleted_evidence_matches_normalized_relative_paths(tmp_path):
    repo, _ = repository(tmp_path)
    doc = repo / 'docs/system/interfaces/api.md'
    doc.write_text(doc.read_text().replace('path: src/service.py', 'path: ./src/service.py'))
    base = commit(repo)
    (repo / 'src/service.py').unlink()
    ctx = fact_context(repo, commit(repo), base)
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
        changed = schema if dependency == 'generated-source' else generator
    base = commit(repo)
    changed.write_text(changed.read_text() + '\n# changed\n')
    ctx = fact_context(repo, commit(repo), base)
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
    ctx = fact_context(shallow, head, head)
    assert ctx['audit']['findings'] == []


@pytest.mark.parametrize('extra', [[], ['--scope', 'full'], ['--scope', 'branch'], ['--base', 'HEAD'],
                                  ['--implementation-path', 'src/service.py']])
def test_commit_audit_rejects_incomplete_or_mixed_arguments(python_exe, tmp_path, extra):
    repo, base = repository(tmp_path)
    args = ['--source-commit', base]
    if extra:
        args += ['--target-commit', base, *extra]
    result = mdf(python_exe, 'fact-audit', '--repo', str(repo), *args)
    assert result.returncode != 0 and 'invalid_arguments' in result.stderr


@pytest.mark.parametrize('case', ['unrelated', 'multiple', 'missing'])
def test_commit_audit_rejects_invalid_history(tmp_path, case):
    repo, base = repository(tmp_path)
    tree = git(repo, 'rev-parse', base + '^{tree}').stdout.strip()
    if case == 'missing':
        source, target = 'absent-ref', base
    elif case == 'unrelated':
        source = git(repo, 'commit-tree', tree, '-m', 'root').stdout.strip()
        target = base
    else:
        left = git(repo, 'commit-tree', tree, '-p', base, '-m', 'left').stdout.strip()
        right = git(repo, 'commit-tree', tree, '-p', base, '-m', 'right').stdout.strip()
        source = git(repo, 'commit-tree', tree, '-p', left, '-p', right, '-m', 'merge1').stdout.strip()
        target = git(repo, 'commit-tree', tree, '-p', right, '-p', left, '-m', 'merge2').stdout.strip()
    with pytest.raises(MDFError):
        fact_context(repo, source, target)


def test_snapshot_does_not_run_filters_or_follow_symlinks(tmp_path, monkeypatch):
    repo, base = repository(tmp_path)
    marker = tmp_path / 'ran-filter'
    git(repo, 'config', 'filter.hostile.smudge', f'touch {marker}')
    (repo / '.gitattributes').write_text('src/* filter=hostile export-ignore\n')
    source = commit(repo)
    config = tmp_path / 'global-config'
    config.write_text('[filter \"hostile\"]\n\tclean = touch ' + str(marker) + '\n')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(config))
    ctx = fact_context(repo, source, base)
    assert not marker.exists() and 'src/service.py' in ctx['source_mappings']['docs/system/interfaces/api.md']
    monkeypatch.delenv('GIT_CONFIG_GLOBAL')
    (repo / 'escape').symlink_to(tmp_path)
    source = commit(repo)
    with pytest.raises(MDFError, match='非普通文件'):
        fact_context(repo, source, base)
    assert not marker.exists()


def test_fact_report_cli_accepts_complete_clean_review(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    ctx = fact_context(repo, base, base)
    report = report_for(ctx)
    assert report['decision'] == 'pass'
    context_file, report_file = tmp_path / 'context.json', tmp_path / 'report.json'
    context_file.write_text(json.dumps(ctx))
    report_file.write_text(json.dumps(report))
    result = payload(mdf(python_exe, 'fact-audit-report-check', '--context-file', str(context_file),
                         '--report-file', str(report_file)))
    assert result['result']['decision'] == 'pass'


@pytest.mark.parametrize('damage', ['fingerprint', 'head', 'coverage', 'warning', 'semantic', 'validation', 'incomplete'])
def test_fact_report_rejects_false_pass(tmp_path, damage):
    repo, base = repository(tmp_path)
    (repo / 'src/new.py').write_text('VALUE = 1\n')
    ctx = fact_context(repo, commit(repo), base)
    report = report_for(ctx)
    report['decision'] = 'pass'
    if damage == 'fingerprint':
        ctx['diff'] = 'forged'
    elif damage == 'head':
        report['review_head'] = base
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
    ctx = fact_context(repo, commit(repo), base)
    report = report_for(ctx)
    assert validate_fact_report(ctx, report)['decision'] == 'changes_requested'
    report.update(document_paths=[], incomplete=['事实页尚未复核'], decision='needs-review')
    assert validate_fact_report(ctx, report)['decision'] == 'needs-review'


@pytest.mark.parametrize('field,value', [('audit', None), ('audit', {}), ('paths', None),
                                        ('document_paths', [{}])])
def test_fact_report_rejects_malformed_context_with_structured_error(tmp_path, field, value):
    from mdf_core.reviewing.context import fingerprint
    repo, base = repository(tmp_path)
    ctx = fact_context(repo, base, base)
    report = report_for(ctx)
    ctx[field] = value
    ctx['context_sha256'] = fingerprint({k: v for k, v in ctx.items() if k != 'context_sha256'})
    report['context_sha256'] = ctx['context_sha256']
    with pytest.raises(MDFError):
        validate_fact_report(ctx, report)


@pytest.mark.parametrize('roots', ['null', '[1]', '[{}]'])
def test_commit_audit_rejects_malformed_roots_with_structured_error(tmp_path, roots):
    repo, base = repository(tmp_path)
    manifest = repo / '.mdf/manifest.yaml'
    manifest.write_text(manifest.read_text().replace('implementation_roots: [src]', 'implementation_roots: ' + roots))
    source = commit(repo)
    with pytest.raises(MDFError, match='implementation_roots'):
        fact_context(repo, source, base)


@pytest.mark.parametrize('root', ['.', './src'])
def test_commit_audit_normalizes_implementation_roots(tmp_path, root):
    repo, _ = repository(tmp_path)
    manifest = repo / '.mdf/manifest.yaml'
    manifest.write_text(manifest.read_text().replace('implementation_roots: [src]', f'implementation_roots: [{root}]'))
    base = commit(repo)
    (repo / 'src/config.json').write_text('{"enabled": true}\n')
    ctx = fact_context(repo, commit(repo), base)
    assert 'src/config.json' in ctx['implementation_paths']
