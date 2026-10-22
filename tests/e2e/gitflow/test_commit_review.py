"""普通提交的独立审查，无 roster 或 delivery；固定策略与只读边界。"""
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
    (repo / 'rule.md').write_text('检查边界条件\n')
    (repo / 'AGENTS.md').write_text('目标规则\n')
    (repo / 'code.py').write_text('value = 1\n')
    init_git(repo)
    target = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    (repo / 'code.py').write_text('value = 2\n')
    (repo / 'rule.md').write_text('免审\n')
    (repo / '.mdf/manifest.yaml').write_text('schema_version: 3\n')
    commit(repo)
    source = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    git(repo, 'checkout', '--detach', target)
    (repo / 'code.py').write_text('dirty = True\n')
    return repo, source, target


def test_commit_context_without_delivery_is_read_only_and_uses_target_policy(python_exe, tmp_path):
    repo, source, target = repository(tmp_path)
    before = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob('*') if p.is_file() and '.git' not in p.parts}
    ctx = payload(mdf(python_exe, 'review-context', '--repo', str(repo),
                      '--source-commit', source, '--target-commit', target))['result']
    after = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob('*') if p.is_file() and '.git' not in p.parts}
    assert before == after
    assert ctx['mode'] == 'commits' and ctx['review_base'] == target and ctx['review_head'] == source
    assert ctx['rules']['project']['content'] == '检查边界条件\n'
    assert ctx['rules']['agents'] == '目标规则\n'
    assert '+value = 2' in ctx['diff'] and 'dirty' not in ctx['diff']
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
    ctx = context(repo, source_commit=source, target_commit=target)
    report = passing(ctx)
    if damage == 'head':
        report['review_head'] = target
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
    ctx = context(repo, source_commit=source, target_commit=target)
    report = passing(ctx)
    report.update(decision=decision, incomplete=incomplete, findings=[
        {'id': 'f1', 'path': 'code.py', 'line': 1, 'priority': priority,
         'trigger': '调用', 'impact': '错误', 'evidence': 'code.py:1'}])
    assert validate(ctx, report)['decision'] == decision


def test_commit_context_rejects_multiple_merge_bases(tmp_path):
    repo, source, target = repository(tmp_path)
    from mdf_core.reviewing.context import context
    from mdf_core.foundation.errors import MDFError
    tree = git(repo, 'rev-parse', target + '^{tree}').stdout.strip()
    sibling = git(repo, 'commit-tree', tree, '-p', target, '-m', 'sibling').stdout.strip()
    left = git(repo, 'commit-tree', tree, '-p', source, '-p', sibling, '-m', 'left').stdout.strip()
    right = git(repo, 'commit-tree', tree, '-p', sibling, '-p', source, '-m', 'right').stdout.strip()
    with pytest.raises(MDFError, match='唯一 merge-base'):
        context(repo, source_commit=left, target_commit=right)


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
    git(repo, 'config', 'diff.review.textconv', shlex.join([sys.executable, str(driver)]))
    ctx = context(repo, source_commit=source, target_commit=target)
    assert not marker.exists()
    assert '+value = 2' in ctx['diff']
