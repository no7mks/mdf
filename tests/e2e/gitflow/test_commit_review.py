"""普通提交的独立审查，无 roster 或 delivery；要求 clean HEAD。"""
import json

import pytest

from mdf_test_support import git, mdf, payload, init_git
from support_delivery import commit
from test_ci_review import passing


def repository(tmp_path):
    repo = tmp_path / 'plain'
    repo.mkdir()
    (repo / '.mdf').mkdir()
    (repo / '.mdf/manifest.yaml').write_text('schema_version: 3\nrules:\n  code-review: rule.md\n')
    from mdf_test_support import copy_fixture
    (repo / '.mdf/modules.yaml').write_text((copy_fixture(tmp_path / 'fixture') / '.mdf/modules.yaml').read_text()
                                          .replace('"src/**"', '"code.py"', 1))
    (repo / 'rule.md').write_text('检查边界条件\n')
    (repo / 'AGENTS.md').write_text('目标规则\n')
    (repo / 'code.py').write_text('value = 1\n')
    init_git(repo)
    target = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    (repo / 'code.py').write_text('value = 2\n')
    (repo / 'rule.md').write_text('免审\n')
    (repo / '.mdf/manifest.yaml').write_text('schema_version: 3\nrules:\n  code-review: rule.md\n')
    (repo / 'AGENTS.md').write_text('后续 Agent 规则\n')
    commit(repo)
    source = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    git(repo, 'checkout', '--detach', source)
    return repo, source, target


def test_commit_context_without_delivery_is_read_only_and_uses_current_policy(python_exe, tmp_path):
    repo, source, target = repository(tmp_path)
    before = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob('*') if p.is_file() and '.git' not in p.parts}
    ctx = payload(mdf(python_exe, 'review-context', '--repo', str(repo),
                      '--against', target))['result']
    after = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob('*') if p.is_file() and '.git' not in p.parts}
    assert before == after
    assert ctx['mode'] == 'against' and ctx['against'] == target and ctx['head'] == source
    assert ctx['rules']['project']['content'] == '免审\n'
    assert ctx['rules']['agents'] == '后续 Agent 规则\n'
    assert '+value = 2' in ctx['diff']
    assert not {'roster', 'source', 'delivery_base', 'artifacts', 'kind', 'target'} & ctx.keys()
    assert ctx['incomplete'] == []
    context_file, report_file = tmp_path / 'context.json', tmp_path / 'report.json'
    context_file.write_text(json.dumps(ctx))
    report_file.write_text(json.dumps(passing(ctx)))
    result = payload(mdf(python_exe, 'review-report-check', '--context-file', str(context_file),
                         '--report-file', str(report_file)))
    assert result['result']['valid'] and result['result']['decision'] == 'pass'


@pytest.mark.parametrize('damage', ['head', 'rules', 'context', 'coverage', 'blocking', 'incomplete', 'empty_changes'])
def test_commit_report_cannot_forge_pass(python_exe, tmp_path, damage):
    repo, source, target = repository(tmp_path)
    from mdf_core.reviewing.context import context
    from mdf_core.reviewing.report import validate
    from mdf_core.foundation.errors import MDFError
    ctx = context(repo, against=target)
    report = passing(ctx)
    if damage == 'head':
        report['head'] = 'wrong'
    elif damage == 'rules':
        report['rules_sha256'] = 'wrong'
    elif damage == 'context':
        ctx['diff'] = 'forged'
    elif damage == 'coverage':
        report['paths'] = []
    elif damage == 'blocking':
        report['findings'] = [{'id': 'f1', 'path': 'code.py', 'line': 1, 'priority': 1,
                               'trigger': '调用', 'impact': '错误', 'evidence': 'code.py:1'}]
    elif damage == 'incomplete':
        report['incomplete'] = ['缺证据']
    else:
        report['decision'] = 'changes_requested'
    with pytest.raises(MDFError):
        validate(ctx, report)


@pytest.mark.parametrize('decision,priority,incomplete', [
    ('changes_requested', 1, []), ('pass', 2, []), ('needs-review', 1, ['待核实']), ('error', 1, ['执行失败'])])
def test_commit_report_accepts_supported_outcomes(tmp_path, decision, priority, incomplete):
    repo, source, target = repository(tmp_path)
    from mdf_core.reviewing.context import context
    from mdf_core.reviewing.report import validate
    ctx = context(repo, against=target)
    report = passing(ctx)
    report.update(decision=decision, incomplete=incomplete, findings=[
        {'id': 'f1', 'path': 'code.py', 'line': 1, 'priority': priority,
         'trigger': '调用', 'impact': '错误', 'evidence': 'code.py:1'}])
    assert validate(ctx, report)['decision'] == decision


def test_against_uses_exact_version_instead_of_merge_base(tmp_path):
    from mdf_core.reviewing.context import context
    repo, source, target = repository(tmp_path)
    # source 是当前 HEAD；对更早的 target 比较，不退回共同祖先以外的语义。
    ctx = context(repo, against=target)
    assert ctx['against'] == target and ctx['head'] == source
    assert '-value = 1' in ctx['diff'] and '+value = 2' in ctx['diff']


def test_commit_context_does_not_execute_textconv(tmp_path):
    import shlex
    import sys
    from mdf_core.reviewing.context import context
    repo, source, target = repository(tmp_path)
    marker = tmp_path / 'textconv-executed'
    driver = tmp_path / 'convert.py'
    driver.write_text('from pathlib import Path\n'
                      + f'Path({str(marker)!r}).write_text("executed")\n'
                      + 'print("masked diff")\n')
    (repo / '.gitattributes').write_text('code.py diff=review\n')
    git(repo, 'add', '.gitattributes')
    git(repo, 'commit', '-m', 'test: gitattributes')
    git(repo, 'config', 'diff.review.textconv', shlex.join([sys.executable, str(driver)]))
    ctx = context(repo, against=target)
    assert not marker.exists()
    assert '+value = 2' in ctx['diff']


def test_current_rule_change_updates_fingerprint_without_changing_commit_scope(tmp_path):
    from mdf_core.reviewing.context import context
    repo, source, target = repository(tmp_path)
    before = context(repo, against=target)
    (repo / 'rule.md').write_text('更新后的当前规则\n')
    git(repo, 'add', 'rule.md')
    git(repo, 'commit', '-m', 'test: 更新规则')
    after = context(repo, against=target)
    assert after['rules']['project']['content'] == '更新后的当前规则\n'
    assert before['rules_sha256'] != after['rules_sha256']
    assert before['context_sha256'] != after['context_sha256']
    assert before['against'] == after['against']
    assert before['head'] != after['head']


def test_rule_path_comes_from_current_manifest(tmp_path):
    from mdf_core.reviewing.context import context
    repo, source, target = repository(tmp_path)
    (repo / '.mdf/manifest.yaml').write_text('schema_version: 3\nrules:\n  code-review: AGENTS.md\n')
    git(repo, 'add', '.mdf/manifest.yaml')
    git(repo, 'commit', '-m', 'test: 改 rule 路径')
    ctx = context(repo, against=target)
    assert ctx['rules']['project']['path'] == 'AGENTS.md'
    assert ctx['rules']['project']['content'] == '后续 Agent 规则\n'


def test_missing_current_rule_does_not_fall_back_to_target(tmp_path):
    from mdf_core.reviewing.context import context
    from mdf_core.foundation.errors import MDFError
    repo, source, target = repository(tmp_path)
    (repo / 'rule.md').unlink()
    git(repo, 'add', '-A')
    git(repo, 'commit', '-m', 'test: 删除规则')
    with pytest.raises(MDFError, match='rules.code-review'):
        context(repo, against=target)


def test_dirty_worktree_rejected(tmp_path):
    from mdf_core.reviewing.context import context
    from mdf_core.foundation.errors import MDFError
    repo, source, target = repository(tmp_path)
    (repo / 'code.py').write_text('dirty = True\n')
    with pytest.raises(MDFError, match='clean|dirty_worktree'):
        context(repo, against=target)


def test_against_ignores_replacement_refs(tmp_path):
    from mdf_core.reviewing.context import context
    repo, source, target = repository(tmp_path)
    git(repo, 'replace', target, source)
    ctx = context(repo, against=target)
    assert ctx['against'] == target and ctx['head'] == source
    assert 'code.py' in ctx['paths']
    assert '-value = 1' in ctx['diff'] and '+value = 2' in ctx['diff']
