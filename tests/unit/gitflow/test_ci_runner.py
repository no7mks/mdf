"""不调用真实 LLM，验证 CI 多路执行和失败时的报告边界。"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import skill_dir
from mdf_core.foundation.errors import MDFError
from mdf_core.reviewing.context import fingerprint


def load(name):
    path = skill_dir('mdf') / 'assets/ci' / (name + '.py')
    spec = importlib.util.spec_from_file_location('ci_example_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ctx():
    result = {'schema_version': 3, 'source': 'feature/x', 'target': 'develop', 'kind': 'feature',
              'delivery_base': 'a' * 40, 'review_base': 'a' * 40, 'review_head': 'b' * 40,
              'policy_ref': 'c' * 40, 'rules_sha256': 'rules', 'incomplete': [], 'paths': ['a.py', 'b.py'],
              'round': 'initial', 'roster': {'reviewers': 2, 'review_strategy': 'partition'}, 'previous_report': None}
    result['context_sha256'] = fingerprint(result)
    return result


def report(context, reviewers):
    result = {key: context[key] for key in
              ('source', 'delivery_base', 'review_base', 'review_head', 'policy_ref', 'rules_sha256', 'context_sha256')}
    result.update(schema_version=3, decision='pass', incomplete=[], reviewers=reviewers, adjudications=[])
    return result


def test_ci_runner_keeps_independent_partition_and_owner_boundary(monkeypatch, tmp_path):
    module, context = load('review'), ctx()
    repo = tmp_path / 'checkout'
    repo.mkdir()
    monkeypatch.setattr(module, 'context', lambda *args, **kwargs: context)
    monkeypatch.setattr(module, 'sha', lambda *args: context['review_head'])
    monkeypatch.setattr(module, 'snapshot', lambda *args: ['same', '', ''])
    calls = []
    def invoke(repo, backend, prompt, body, schema, prefix):
        calls.append(body)
        if 'reviewers' in body:
            return report(context, body['reviewers'])
        return {'id': 'r' + str(len(calls)), 'rules_sha256': 'rules', 'paths': body['assigned_paths'],
                'incomplete': [], 'findings': [], 'previous_findings': []}
    monkeypatch.setattr(module, 'invoke', invoke)
    args = SimpleNamespace(repo=str(repo), source='feature/x', head='HEAD', policy_ref='develop',
                           backend='codex', output_dir=str(tmp_path / 'output'))
    assert module.run(args) == 0
    assert calls[0]['assigned_paths'] == ['a.py'] and calls[1]['assigned_paths'] == ['b.py']
    assert 'reviewers' not in calls[0] and 'reviewers' not in calls[1]
    assert len(calls[2]['reviewers']) == 2
    assert json.loads((tmp_path / 'output/checked.json').read_text())['valid']


@pytest.mark.parametrize('raw', ['invalid JSON', '{"type":"result","subtype":"error"}',
                                 '{"subtype":"success","result":"not JSON"}'])
def test_cursor_output_failure_keeps_logs(monkeypatch, tmp_path, raw):
    module = load('review')
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout=raw, stderr='details'))
    with pytest.raises(MDFError):
        module.invoke(tmp_path, 'cursor', 'review', {}, tmp_path / 'schema', tmp_path / 'reviewer')
    assert (tmp_path / 'reviewer.stdout.log').read_text() == raw
    assert (tmp_path / 'reviewer.stderr.log').read_text() == 'details'


def test_ci_runner_rejects_output_directory_in_checkout(tmp_path):
    module = load('review')
    args = SimpleNamespace(repo=str(tmp_path), output_dir=str(tmp_path / 'output'))
    with pytest.raises(MDFError, match='checkout 外'):
        module.run(args)


def test_publisher_stale_head_does_not_publish(monkeypatch, tmp_path):
    module, context = load('publish'), ctx()
    reviewers = [{'id': f'r{i}', 'rules_sha256': 'rules', 'paths': [path], 'incomplete': [],
                  'findings': [], 'previous_findings': []} for i, path in enumerate(context['paths'])]
    (tmp_path / 'context.json').write_text(json.dumps(context))
    (tmp_path / 'report.json').write_text(json.dumps(report(context, reviewers)))
    class Forge:
        def get(self, number):
            return {'state': 'open', 'source': 'feature/x', 'target': 'develop', 'head': 'changed'}
        def api(self, *args):
            pytest.fail('陈旧 head 不得发写请求')
    monkeypatch.setattr(module, 'origin', lambda *args: {})
    monkeypatch.setattr(module, 'Forge', lambda *args: Forge())
    args = SimpleNamespace(repo=str(tmp_path), provider='github', number=1,
                           context_file=str(tmp_path / 'context.json'), report_file=str(tmp_path / 'report.json'))
    with pytest.raises(ValueError, match='已变化'):
        module.publish(args)


def test_ci_runner_detects_reviewer_writing_checkout(monkeypatch, tmp_path):
    from support_delivery import local_repo
    module, context = load('review'), ctx()
    repo = local_repo(tmp_path)
    monkeypatch.setattr(module, 'context', lambda *args, **kwargs: context)
    monkeypatch.setattr(module, 'sha', lambda *args: context['review_head'])
    def invoke(*args):
        (repo / 'unexpected.txt').write_text('reviewer 越界修改\n')
        return {'id': 'r1', 'paths': ['a.py']}
    monkeypatch.setattr(module, 'invoke', invoke)
    args = SimpleNamespace(repo=str(repo), source='feature/x', head='HEAD', policy_ref='develop',
                           backend='cursor', output_dir=str(tmp_path / 'output'))
    with pytest.raises(MDFError, match='只读边界'):
        module.run(args)
    assert (repo / 'unexpected.txt').exists()


def test_ci_runner_refuses_dirty_checkout_before_starting_llm(monkeypatch, tmp_path):
    from support_delivery import local_repo
    module, context = load('review'), ctx()
    repo = local_repo(tmp_path)
    (repo / 'src/service.py').write_text('uncommitted = True\n')
    monkeypatch.setattr(module, 'context', lambda *args, **kwargs: context)
    monkeypatch.setattr(module, 'sha', lambda *args: context['review_head'])
    monkeypatch.setattr(module, 'invoke', lambda *args: pytest.fail('脏 checkout 不得启动 LLM'))
    args = SimpleNamespace(repo=str(repo), source='feature/x', head='HEAD', policy_ref='develop',
                           backend='codex', output_dir=str(tmp_path / 'output'))
    with pytest.raises(MDFError, match='checkout 必须干净'):
        module.run(args)


@pytest.mark.parametrize('mutates', [False, True])
def test_commit_runner_uses_one_report_without_roster(monkeypatch, tmp_path, mutates):
    from support_delivery import local_repo
    from mdf_core.reviewing.context import context as make_context
    module = load('review')
    repo = local_repo(tmp_path)
    context = make_context(repo, against='HEAD')
    calls = []
    def invoke(repo, backend, prompt, body, schema, prefix):
        calls.append(body)
        assert schema.name == 'against-review-report.schema.json'
        assert 'roster' not in body['context'] and 'reviewers' not in body
        if mutates:
            (repo / 'unexpected.txt').write_text('越界\n')
        keys = ('schema_version', 'mode', 'against', 'worktree_sha256',
                'rules_sha256', 'context_sha256', 'paths')
        return {**{key: context[key] for key in keys}, 'decision': 'pass', 'incomplete': [], 'findings': []}
    monkeypatch.setattr(module, 'invoke', invoke)
    args = SimpleNamespace(repo=str(repo), source=None, head=None, policy_ref=None,
                           against='HEAD', backend='codex',
                           output_dir=str(tmp_path / 'output'))
    if mutates:
        with pytest.raises(MDFError, match='修改了 checkout'):
            module.run(args)
    else:
        assert module.run(args) == 0
        assert json.loads((tmp_path / 'output/checked.json').read_text())['valid']
    assert len(calls) == 1
