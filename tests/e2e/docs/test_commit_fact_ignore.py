"""独立 commit fact audit 的 source ignore 归属、结构与指纹回归。"""
import json

import pytest

from mdf_test_support import git
from mdf_core.foundation.errors import MDFError
from mdf_core.reviewing.context import fingerprint
from mdf_core.reviewing.fact_context import fact_context
from mdf_core.reviewing.fact_report import validate_fact_report
from test_commit_fact_audit import commit, repository, report_for


@pytest.mark.parametrize('change', ['remove', 'narrow'])
def test_source_module_ignore_removal_restores_review(tmp_path, change):
    repo, _ = repository(tmp_path)
    vendor = repo / 'src/generated/tool.py'
    vendor.parent.mkdir(parents=True)
    vendor.write_text('VALUE = 1\n')
    modules = repo / '.mdf/modules.yaml'
    original = modules.read_text()
    modules.write_text(original.replace('    ignore: []',
        '    ignore:\n      - pattern: src/generated/**\n        reason: generated'))
    target = commit(repo)
    modules.write_text(original if change == 'remove' else modules.read_text().replace('pattern: src/generated/**', 'pattern: src/generated/kept.py'))
    if change == 'narrow':
        vendor.with_name('kept.py').write_text('VALUE = 1\n')
    vendor.write_text('VALUE = 2\n')
    source = commit(repo)
    ctx = fact_context(repo, target[:12])
    rel = vendor.relative_to(repo).as_posix()
    assert ctx['against'] == target
    assert rel in ctx['paths'] and rel in ctx['implementation_paths']
    assert f'diff --git a/{rel}' in ctx['diff']
    assert not any(row['path'] == rel for row in ctx['ignored'])
    assert ctx['rules']['modules'] == modules.read_text()
    assert ctx['rules_sha256'] == fingerprint(ctx['rules'])
    report = report_for(ctx)
    ctx['rules']['modules'] += '# forged\n'
    with pytest.raises(MDFError, match='指纹'):
        validate_fact_report(ctx, report)


@pytest.mark.parametrize('owners', ['outside', 'one', 'all'])
def test_module_ignore_ownership_uses_source_sourcesets(tmp_path, owners):
    repo, target = repository(tmp_path)
    modules = repo / '.mdf/modules.yaml'
    original = modules.read_text()
    module = original.split('  default:\n', 1)[1]
    ignored_module = module.replace('    ignore: []',
        '    ignore:\n      - pattern: src/new.py\n        reason: generated')
    if owners == 'outside':
        config = 'modules:\n  default:\n' + ignored_module.replace('src/**', 'other/**')
    else:
        other = ignored_module if owners == 'all' else module
        config = 'modules:\n  default:\n' + ignored_module + '  overlapping:\n' + other
    modules.write_text(config)
    (repo / 'src/new.py').write_text('VALUE = 2\n')
    ctx = fact_context(repo, target)
    excluded = owners in {'all', 'outside'}
    assert ('src/new.py' not in ctx['paths']) == excluded
    assert ('src/new.py' not in ctx['implementation_paths']) == excluded
    assert ('src/new.py' not in ctx['audit']['implementation_paths']) == excluded
    assert bool(ctx['ignored']) == (owners == 'all')
    assert ('diff --git a/src/new.py' not in ctx['diff']) == excluded
    assert (not any(w['path'] == 'src/new.py' for w in ctx['audit']['warnings'])) == excluded


@pytest.mark.parametrize('change', ['delete', 'rename', 'never-matched'])
def test_source_module_ignore_validates_base_and_source_files(tmp_path, change):
    repo, base = repository(tmp_path)
    generated = repo / 'src/generated.py'
    if change != 'never-matched':
        generated.write_text('VALUE = 1\n')
    target = commit(repo) if change != 'never-matched' else base
    modules = repo / '.mdf/modules.yaml'
    modules.write_text(modules.read_text().replace('    ignore: []',
        '    ignore:\n      - pattern: src/generated.py\n        reason: generated'))
    if change == 'delete':
        generated.unlink()
    elif change == 'rename':
        generated.rename(repo / 'src/renamed.py')
    ctx = fact_context(repo, target)
    empty = [f for f in ctx['audit']['findings'] if f['code'] == 'audit.ignore_empty']
    assert bool(empty) == (change == 'never-matched')
    assert 'src/generated.py' not in ctx['paths']
    if change != 'never-matched':
        assert ctx['ignored'] == [{'path': 'src/generated.py', 'ignore_path': 'src/generated.py', 'reason': 'generated'}]
    if change == 'rename':
        assert 'src/renamed.py' in ctx['paths']
        assert 'src/renamed.py' in ctx['audit']['implementation_paths']


@pytest.mark.parametrize('invalid', ['missing', 'yaml', 'repo-ignore', 'module-ignore'])
def test_invalid_source_modules_fail_without_target_fallback(tmp_path, invalid):
    repo, target = repository(tmp_path)
    modules = repo / '.mdf/modules.yaml'
    if invalid == 'missing':
        modules.unlink()
    elif invalid == 'yaml':
        modules.write_text('[]\n')
    elif invalid == 'repo-ignore':
        modules.write_text('ignore: [bad]\n' + modules.read_text())
    else:
        modules.write_text(modules.read_text().replace('ignore: []', 'ignore: [bad]'))
    with pytest.raises(MDFError):
        fact_context(repo, target)


@pytest.mark.parametrize('ignored_document', [False, True])
def test_source_ignore_filters_document_structure_independently(tmp_path, ignored_document):
    repo, target = repository(tmp_path)
    doc = repo / 'docs/system/interfaces/api.md'
    # Stable sections avoid prose-length noise; the document exceeds its role line limit.
    doc.write_text(doc.read_text() + '\n## Details\n' + '- detail\n' * 600)
    modules = repo / '.mdf/modules.yaml'
    pattern = 'docs/system/interfaces/api.md' if ignored_document else 'src/service.py'
    modules.write_text(modules.read_text().replace('"src/**"', '"**"', 1).replace('    ignore: []',
        f'    ignore:\n      - pattern: {pattern}\n        reason: excluded'))
    (repo / 'src/service.py').write_text('VALUE = 2\n')
    ctx = fact_context(repo, target)
    rel = doc.relative_to(repo).as_posix()
    assert (rel not in ctx['document_paths']) == ignored_document
    assert (rel not in ctx['audit']['document_paths']) == ignored_document
    assert (not any(f['code'] == 'size.hard' and f['path'] == rel
                    for f in ctx['audit']['findings'])) == ignored_document
    assert (not any(row['path'] == rel for row in ctx['ignored'])) != ignored_document


@pytest.mark.parametrize('field', ['paths', 'implementation_paths', 'document_paths'])
def test_report_rejects_paths_outside_source_ignore_context(tmp_path, field):
    repo, target = repository(tmp_path)
    modules = repo / '.mdf/modules.yaml'
    modules.write_text(modules.read_text().replace('    ignore: []',
        '    ignore:\n      - pattern: src/service.py\n        reason: excluded'))
    (repo / 'src/service.py').write_text('VALUE = 2\n')
    ctx = fact_context(repo, target)
    report = json.loads(json.dumps(report_for(ctx)))
    report[field].append('src/service.py')
    with pytest.raises(MDFError, match='超出范围'):
        validate_fact_report(ctx, report)


@pytest.mark.parametrize('scope', ['full', 'branch', 'paths'])
@pytest.mark.parametrize('prefix', ['', './'])
def test_owned_configuration_outside_implementation_roots(python_exe, tmp_path, scope, prefix):
    from mdf_test_support import mdf, payload
    repo, _ = repository(tmp_path)
    modules = repo / '.mdf/modules.yaml'
    modules.write_text(modules.read_text().replace('"src/**"', '"src/**"\n      - "config/**"', 1))
    base = commit(repo)
    config = repo / 'config/runtime.json'
    config.parent.mkdir()
    config.write_text('{"enabled": true}\n')
    vendor = repo / '.codex/skills/mdf/runtime.json'
    vendor.parent.mkdir(parents=True)
    vendor.write_text('{"internal": true}\n')
    source = commit(repo)
    args = ['--base', base] if scope == 'branch' else []
    if scope == 'paths':
        args = ['--implementation-path', prefix + 'config/runtime.json']
    result = payload(mdf(python_exe, 'fact-audit', '--repo', str(repo), '--scope', scope, *args))
    assert 'config/runtime.json' in result['implementation_paths']
    assert '.codex/skills/mdf/runtime.json' not in result['implementation_paths']
    ctx = fact_context(repo, base)
    assert ctx['paths'] == ctx['implementation_paths'] == ['config/runtime.json']
    assert '.codex/skills/mdf' not in ctx['diff']


def test_fact_context_uses_current_policy_and_current_scope(tmp_path):
    repo, target = repository(tmp_path)
    (repo / 'src/new.py').write_text('VALUE = 1\n')
    source = commit(repo)
    before = fact_context(repo, target)
    (repo / 'AGENTS.md').write_text('当前工作区审阅规则\n')
    modules = repo / '.mdf/modules.yaml'
    modules.write_text(modules.read_text().replace('src/**', 'other/**'))
    after = fact_context(repo, target)
    assert after['rules']['agents'] == '当前工作区审阅规则\n'
    assert after['rules']['modules'] == modules.read_text()
    assert before['rules_sha256'] != after['rules_sha256']
    assert before['implementation_paths'] == ['src/new.py']
    assert after['implementation_paths'] == [] and 'src/new.py' not in after['diff']
    assert 'AGENTS.md' in after['paths']
