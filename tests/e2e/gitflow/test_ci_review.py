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
