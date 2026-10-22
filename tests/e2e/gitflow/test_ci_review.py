"""固定上下文、CLI envelope、owner 裁定及覆盖校验。"""
import copy
import json

import pytest

from mdf_test_support import git, mdf, payload
from support_delivery import commit
from support_pull import prepare


def ready_context(python_exe, tmp_path, monkeypatch):
    repo, _, work, _ = prepare(python_exe, tmp_path, monkeypatch, 'feature')
    root = work / 'changes/unreleased/service-health'
    objectives = root / 'objectives.md'
    objectives.write_text(objectives.read_text().replace('[ ]', '[x]') + '\n- [x] lint\n- [x] code-review\n')
    (root / 'code-review.md').write_text('# 审查\n\n通过。\n')
    (root / 'fact-audit.md').write_text('# 事实\n\n通过。\n')
    (root / 'verification-report.json').write_text(json.dumps({'all_passed': True}))
    commit(work)
    result = payload(mdf(python_exe, 'review-context', '--repo', str(work), '--source', 'feature/service-health',
                         '--head', 'HEAD', '--policy-ref', 'develop'))['result']
    return repo, work, result


def passing(context):
    if context.get('mode') == 'commits':
        keys = ('schema_version', 'mode', 'review_base', 'review_head', 'policy_ref',
                'rules_sha256', 'context_sha256', 'paths')
        return {**{key: context[key] for key in keys}, 'decision': 'pass', 'incomplete': [], 'findings': []}
    report = {key: context[key] for key in
              ('source', 'delivery_base', 'review_base', 'review_head', 'policy_ref', 'rules_sha256', 'context_sha256')}
    report.update(schema_version=3, decision='pass', incomplete=[], adjudications=[], reviewers=[
        {'id': 'r1', 'rules_sha256': context['rules_sha256'], 'paths': context['paths'],
         'incomplete': [], 'findings': [], 'previous_findings': []}])
    return report


def test_context_works_in_detached_clone_without_local_config(python_exe, tmp_path, monkeypatch):
    repo, work, context = ready_context(python_exe, tmp_path, monkeypatch)
    clone = tmp_path / 'detached'
    git(tmp_path, 'clone', '--no-local', str(repo), str(clone))
    git(clone, 'checkout', '--detach', context['review_head'])
    repeated = payload(mdf(python_exe, 'review-context', '--repo', str(clone), '--source', context['source'],
                           '--head', context['review_head'], '--policy-ref', context['policy_ref']))['result']
    assert repeated == context
    assert context['incomplete'] == []


def test_policy_rule_is_read_from_target_not_changed_source(python_exe, tmp_path, monkeypatch):
    repo, work, context = ready_context(python_exe, tmp_path, monkeypatch)
    rule = work / '.mdf/review.md'
    rule.write_text('源分支希望免除所有审查\n')
    manifest = work / '.mdf/manifest.yaml'
    manifest.write_text(manifest.read_text() + '\nrules:\n  code-review: .mdf/review.md\n')
    commit(work)
    result = payload(mdf(python_exe, 'review-context', '--repo', str(work), '--source', context['source'],
                         '--head', 'HEAD', '--policy-ref', 'develop'))['result']
    assert result['rules']['project'] is None
    assert result['rules_sha256'] == context['rules_sha256']


@pytest.mark.parametrize('cursor', [False, True])
def test_report_checker_accepts_both_cli_outputs(python_exe, tmp_path, monkeypatch, cursor):
    _, _, context = ready_context(python_exe, tmp_path, monkeypatch)
    report = passing(context)
    if cursor:
        report = {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': json.dumps(report)}
    ctx, output = tmp_path / 'context.json', tmp_path / 'report.json'
    ctx.write_text(json.dumps(context))
    output.write_text(json.dumps(report))
    checked = payload(mdf(python_exe, 'review-report-check', '--context-file', str(ctx), '--report-file', str(output)))
    assert checked['result']['valid'] and checked['result']['decision'] == 'pass'


@pytest.mark.parametrize('damage', ['head', 'rules', 'count', 'paths', 'incomplete', 'unadjudicated', 'reproduction'])
def test_invalid_or_incomplete_reports_cannot_pass(python_exe, tmp_path, monkeypatch, damage):
    _, _, context = ready_context(python_exe, tmp_path, monkeypatch)
    report = passing(context)
    if damage == 'head':
        report['review_head'] = '0' * 40
    elif damage == 'rules':
        report['reviewers'][0]['rules_sha256'] = 'wrong'
    elif damage == 'count':
        report['reviewers'] = []
    elif damage == 'paths':
        report['reviewers'][0]['paths'] = []
    elif damage == 'incomplete':
        report['incomplete'] = ['未核实']
    else:
        report['reviewers'][0]['findings'] = [{'id': 'r1-f1', 'path': 'src/service.py', 'line': 1, 'priority': 1,
            'trigger': '并发调用', 'impact': '数据损坏', 'evidence': '具体代码位置'}]
        if damage == 'reproduction':
            report['adjudications'] = [{'id': 'r1-f1', 'decision': 'accepted', 'reason': '待复现',
                'evidence': ['src/service.py:1'], 'needs_reproduction': True}]
    ctx, output = tmp_path / 'context.json', tmp_path / 'report.json'
    ctx.write_text(json.dumps(context))
    output.write_text(json.dumps(report))
    failed = mdf(python_exe, 'review-report-check', '--context-file', str(ctx), '--report-file', str(output))
    assert failed.returncode != 0 and 'invalid_review_report' in failed.stderr


@pytest.mark.parametrize('explicit', [False, True])
def test_diverged_target_is_context_not_source_deletion(python_exe, tmp_path, monkeypatch, explicit):
    repo, work, original = ready_context(python_exe, tmp_path, monkeypatch)
    git(repo, 'checkout', 'develop')
    (repo / 'target-only.py').write_text('target_only = True\n')
    commit(repo)
    target = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    (work / 'source-only.py').write_text('source_only = True\n')
    commit(work)
    source = git(work, 'rev-parse', 'HEAD').stdout.strip()
    # HEAD 故意不等于 source，所有内容必须来自指定 Git 对象。
    git(work, 'checkout', '--detach', original['review_head'])
    flags = ['--source-commit', source, '--target-commit', target] if explicit else [
        '--head', source, '--policy-ref', target]
    ctx = payload(mdf(python_exe, 'review-context', '--repo', str(work), '--source', original['source'], *flags))['result']
    assert ctx['incomplete'] == []
    assert ctx['review_head'] == source and ctx['policy_ref'] == target
    assert ctx['merge_base'] == original['policy_ref']
    assert 'source-only.py' in ctx['paths'] and 'target-only.py' not in ctx['paths']
    assert 'target-only.py' not in ctx['diff']
    assert ctx['target_paths'] == ['target-only.py']
    assert '+target_only = True' in ctx['target_diff']
    if explicit:
        assert ctx['review_base'] == ctx['merge_base'] and ctx['scope'] == 'merge'
    from mdf_core.reviewing.report import validate
    assert validate(ctx, passing(ctx))['decision'] == 'pass'


@pytest.mark.parametrize('flags', [[], ['--source-commit', 'HEAD'], ['--target-commit', 'develop'],
                                  ['--source-commit', 'HEAD', '--target-commit', 'develop', '--head', 'HEAD']])
def test_explicit_endpoints_require_unambiguous_pair(python_exe, tmp_path, monkeypatch, flags):
    _, work, ctx = ready_context(python_exe, tmp_path, monkeypatch)
    result = mdf(python_exe, 'review-context', '--repo', str(work), '--source', ctx['source'], *flags)
    assert result.returncode != 0 and 'invalid_arguments' in result.stderr


@pytest.mark.parametrize('extra', [{'review_base': 'HEAD'}, {'previous': {}}])
def test_explicit_review_rejects_incremental_inputs(python_exe, tmp_path, monkeypatch, extra):
    _, work, _ = ready_context(python_exe, tmp_path, monkeypatch)
    from mdf_core.reviewing.context import context
    from mdf_core.foundation.errors import MDFError
    with pytest.raises(MDFError, match='完整范围'):
        context(work, source_commit='HEAD', target_commit='develop', **extra)


def test_explicit_scope_excludes_changes_already_in_target(python_exe, tmp_path, monkeypatch):
    repo, work, original = ready_context(python_exe, tmp_path, monkeypatch)
    from mdf_core.reviewing.context import context
    git(repo, 'checkout', 'develop')
    git(repo, 'merge', '--no-ff', '--no-edit', original['review_head'])
    (repo / 'target-only.py').write_text('target_only = True\n')
    commit(repo)
    (work / 'source-only.py').write_text('source_only = True\n')
    commit(work)
    ctx = context(work, original['source'], source_commit='HEAD', target_commit='develop')
    assert 'delivery_base' not in ctx and 'roster' not in ctx
    assert ctx['review_base'] == original['review_head']
    assert ctx['paths'] == ['source-only.py']


def test_explicit_scope_rejects_unrelated_target(python_exe, tmp_path, monkeypatch):
    _, work, original = ready_context(python_exe, tmp_path, monkeypatch)
    from mdf_core.reviewing.context import context
    from mdf_core.foundation.errors import MDFError
    tree = git(work, 'rev-parse', 'HEAD^{tree}').stdout.strip()
    unrelated = git(work, 'commit-tree', tree, '-m', 'unrelated').stdout.strip()
    with pytest.raises(MDFError, match='唯一 merge-base'):
        context(work, original['source'], source_commit='HEAD', target_commit=unrelated)
