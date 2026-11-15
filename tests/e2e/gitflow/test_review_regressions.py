"""独立审查发现的 CI 与回合恢复缺陷。"""
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import skill_dir
from mdf_core.foundation.errors import MDFError
from mdf_core.reviewing.context import fingerprint
from mdf_core.reviewing.report import validate
from mdf_test_support import git, mdf, payload
from support_delivery import commit
from support_pull import prepare, squash_pending


def completed_materials(work, version='1.2.1'):
    root = work / 'changes/unreleased' / version
    objectives = root / 'objectives.md'
    objectives.write_text(objectives.read_text().replace('[ ]', '[x]') + '\n- [x] code-review\n')
    (root / 'code-review.md').write_text('# 审查\n\n通过。\n')
    (root / 'fact-audit.md').write_text('# 事实\n\n通过。\n')
    (root / 'verification-report.json').write_text(json.dumps({'all_passed': True}))
    (root / 'CHANGE.md').write_text('# 已完成交付\n')
    commit(work)


def waiting_backmerge(python_exe, tmp_path, monkeypatch, *, kind='hotfix'):
    from mdf_core.lifecycle import pull_publish
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, kind)
    completed_materials(work)
    squash_pending(work)
    payload(mdf(python_exe, 'pr', '--repo', str(work)))
    merged = platform.merge(1, tmp_path)
    original = pull_publish.git
    def reject(repo, *args, **kwargs):
        if args[0] == 'push' and any(a.endswith(':refs/heads/develop') for a in args):
            return SimpleNamespace(returncode=1, stdout='', stderr='protected develop')
        return original(repo, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(pull_publish, 'git', reject)
        result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert result['status'] == 'published_pending_backmerge'
    return repo, remote, work, platform, result['backmerge'], merged


def test_backmerge_has_reviewable_fixed_context(python_exe, tmp_path, monkeypatch):
    _, _, _, _, record, merged = waiting_backmerge(python_exe, tmp_path, monkeypatch)
    result = payload(mdf(python_exe, 'review-context', '--repo', record['worktree'],
                         '--source', record['source'], '--head', 'HEAD', '--policy-ref', 'origin/develop'))['result']
    assert result['kind'] == 'backmerge' and result['target'] == 'develop'
    assert result['delivery_base'] == record['base']
    assert result['publication']['merge_commit'] == merged
    assert result['incomplete'] == []


def test_backmerge_pushes_directly_after_develop_advances(python_exe, tmp_path, monkeypatch):
    repo, remote, work, platform, record, merged = waiting_backmerge(python_exe, tmp_path, monkeypatch)
    before = record['head']
    tag = git(remote, 'rev-parse', 'v1.2.1').stdout
    other = tmp_path / 'later-develop'
    git(tmp_path, 'clone', '--branch', 'develop', str(remote), str(other))
    (other / 'later.py').write_text('future = True\n')
    commit(other)
    git(other, 'push', 'origin', 'develop')
    back = Path(record['worktree'])
    git(back, 'fetch', 'origin')
    git(back, 'merge', '--no-ff', '--no-edit', 'origin/develop')
    current = git(back, 'rev-parse', 'HEAD').stdout.strip()
    assert current != before
    updated = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert updated['completed'] and updated['backmerge']['head'] == current
    assert len(platform.pulls) == 1
    assert git(remote, 'rev-parse', 'develop').stdout.strip() == current
    ctx = payload(mdf(python_exe, 'review-context', '--repo', str(back), '--source', record['source'],
                      '--head', 'HEAD', '--policy-ref', 'origin/develop'))['result']
    assert ctx['delivery_base'] == record['base'] and ctx['publication']['merge_commit'] == merged
    assert ctx['incomplete'] == []
    assert payload(mdf(python_exe, 'finish-gitflow', '--repo', str(repo),
                       '--source', updated['source']))['completed']
    assert git(remote, 'rev-parse', 'v1.2.1').stdout == tag
    git(repo, 'merge-base', '--is-ancestor', merged, 'origin/develop')



def test_backmerge_resume_preserves_local_fixes_when_remote_already_contains_release(python_exe, tmp_path, monkeypatch):
    _, remote, work, platform, record, merged = waiting_backmerge(python_exe, tmp_path, monkeypatch)
    back = Path(record['worktree'])
    (back / 'resolution.py').write_text('resolved = True\n')
    commit(back)
    expected = git(back, 'rev-parse', 'HEAD').stdout.strip()
    git(remote, 'update-ref', 'refs/heads/develop', merged)
    result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert result['completed'] and len(platform.pulls) == 1
    git(remote, 'merge-base', '--is-ancestor', expected, 'develop')
    assert git(remote, 'show', 'develop:resolution.py').stdout == 'resolved = True\n'


@pytest.mark.parametrize('diverged', [False, True])
def test_release_waits_for_backmerge_fix_before_source_cleanup(python_exe, tmp_path, monkeypatch, diverged):
    repo, remote, work, _, record, merged = waiting_backmerge(python_exe, tmp_path, monkeypatch, kind='release')
    back = Path(record['worktree'])
    published = record['head']
    git(back, 'push', 'origin', 'HEAD:refs/heads/develop')
    assert git(remote, 'rev-parse', 'develop^2').stdout.strip() == merged
    (back / 'resolution.py').write_text('resolved = True\n')
    commit(back)
    fix = git(back, 'rev-parse', 'HEAD').stdout.strip()
    source = git(work, 'branch', '--show-current').stdout.strip()
    source_head = git(work, 'rev-parse', 'HEAD').stdout.strip()
    hook = remote / 'hooks/pre-receive'
    if diverged:
        other = git(back, 'commit-tree', f'{published}^{{tree}}', '-p', published,
                    '-m', 'test: 推进远端 develop').stdout.strip()
        git(back, 'push', 'origin', f'{other}:refs/heads/develop')
    else:
        other = published
        hook.write_text('#!/bin/sh\nwhile read -r old new ref; do\n'
                        '    if [ "$ref" = refs/heads/develop ]; then\n'
                        '        echo "develop push rejected" >&2\n        exit 1\n    fi\ndone\n')
        hook.chmod(0o755)

    args = ('finish-gitflow', '--repo', str(work))
    pending = payload(mdf(python_exe, *args))
    assert pending['status'] == 'published_pending_backmerge' and not pending['completed']
    assert ('请先集成' if diverged else 'develop push rejected') in pending['backmerge']['push_error']
    assert git(remote, 'rev-parse', 'develop').stdout.strip() == other
    assert git(back, 'rev-parse', 'HEAD').stdout.strip() == fix
    for repository in (repo, remote):
        assert git(repository, 'rev-parse', f'refs/heads/{source}').stdout.strip() == source_head

    if diverged:
        git(back, 'fetch', 'origin')
        git(back, 'merge', '--no-ff', '--no-edit', 'origin/develop')
    else:
        hook.unlink()
        git(back, 'push', 'origin', 'HEAD:refs/heads/develop')
    done = payload(mdf(python_exe, *args))
    assert done['completed'] and done['remote_deleted'] and done['deleted'] == source
    git(remote, 'merge-base', '--is-ancestor', fix, 'develop')
    for repository in (repo, remote):
        assert not git(repository, 'for-each-ref', f'refs/heads/{source}').stdout



@pytest.mark.parametrize('retained_action', ['advance', 'remove'])
def test_completed_backmerge_does_not_republish_retained_worktree(python_exe, tmp_path, monkeypatch, retained_action):
    repo, remote, work, platform, record, _ = waiting_backmerge(python_exe, tmp_path, monkeypatch)
    done = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert done['completed']
    expected = git(remote, 'rev-parse', 'develop').stdout
    back = Path(record['worktree'])
    if retained_action == 'advance':
        (back / 'later.py').write_text('unrelated = True\n')
        commit(back)
    else:
        git(repo, 'worktree', 'remove', str(back))
    repeated = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', done['source']))
    assert repeated['completed'] and len(platform.pulls) == 1
    assert git(remote, 'rev-parse', 'develop').stdout == expected


def test_completed_backmerge_stops_if_remote_lost_the_release(python_exe, tmp_path, monkeypatch):
    repo, remote, work, _, record, _ = waiting_backmerge(python_exe, tmp_path, monkeypatch)
    done = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert done['completed']
    back = Path(record['worktree'])
    (back / 'later.py').write_text('unrelated = True\n')
    commit(back)
    retained = git(back, 'rev-parse', 'HEAD').stdout
    git(remote, 'update-ref', 'refs/heads/develop', record['base'])

    retry = mdf(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', done['source'])
    assert retry.returncode != 0 and 'pull_state_changed' in retry.stderr
    assert git(remote, 'rev-parse', 'develop').stdout.strip() == record['base']
    assert git(back, 'rev-parse', 'HEAD').stdout == retained


def incremental_report(state='reopened'):
    old = {'id': 'r1-f1', 'path': 'src/service.py', 'line': 1, 'priority': 1,
           'trigger': '并发访问', 'impact': '数据损坏', 'evidence': '旧审查中的具体代码'}
    previous = {'reviewers': [{'findings': [old]}]}
    context = {'source': 'feature/example', 'delivery_base': '0' * 40, 'review_base': 'a' * 40, 'review_head': 'b' * 40,
               'policy_ref': 'c' * 40, 'rules_sha256': 'rules', 'roster': {'reviewers': 1, 'review_strategy': 'replicate'},
               'round': 'incremental', 'paths': ['src/service.py'], 'incomplete': [], 'previous_report': previous}
    context['context_sha256'] = fingerprint(context)
    report = {k: context[k] for k in
              ('source', 'delivery_base', 'review_base', 'review_head', 'policy_ref', 'rules_sha256', 'context_sha256')}
    report.update(schema_version=3, decision='pass', incomplete=[], adjudications=[], reviewers=[{
        'id': 'r1', 'rules_sha256': 'rules', 'paths': ['src/service.py'], 'findings': [], 'incomplete': [],
        'previous_findings': [{'id': old['id'], 'state': state, 'evidence': '本轮复核证据'}]}])
    return context, report, old


def test_reopened_old_blocker_cannot_pass_without_adjudication():
    context, report, _ = incremental_report()
    with pytest.raises(MDFError, match='未完成|重新打开|reopened|旧问题'):
        validate(context, report)


def test_reopened_old_blocker_can_be_handed_off_as_needs_review():
    context, report, _ = incremental_report()
    report['decision'] = 'needs-review'
    assert validate(context, report)['decision'] == 'needs-review'


def test_reopened_old_blocker_cannot_be_silently_downgraded():
    context, report, finding = incremental_report()
    report['reviewers'][0]['findings'] = [{**finding, 'priority': 3}]
    report['adjudications'] = [{'id': finding['id'], 'decision': 'accepted', 'reason': '改为建议',
                               'evidence': ['src/service.py:1'], 'needs_reproduction': False}]
    with pytest.raises(MDFError, match='改级'):
        validate(context, report)


def test_resolved_old_finding_can_pass():
    context, report, _ = incremental_report('resolved')
    assert validate(context, report)['decision'] == 'pass'


def test_reopened_finding_can_be_adjudicated_as_changes_requested():
    context, report, finding = incremental_report()
    report['reviewers'][0]['findings'] = [finding]
    report['adjudications'] = [{'id': finding['id'], 'decision': 'accepted', 'reason': '旧问题仍然成立',
                               'evidence': ['src/service.py:1'], 'needs_reproduction': False}]
    report['decision'] = 'changes_requested'
    assert validate(context, report)['decision'] == 'changes_requested'


def test_ci_runner_accepts_confirmed_initial_release_base(python_exe, tmp_path, monkeypatch):
    repo, _, work, _ = prepare(python_exe, tmp_path, monkeypatch, 'release')
    path = repo / '.mdf/manifest.yaml'
    path.write_text(re.sub(r'(?m)^  latest_release:.*$', '  latest_release: null', path.read_text()))
    commit(repo)
    git(work, 'merge', '--no-ff', '--no-edit', 'master')
    completed_materials(work)
    policy = git(repo, 'rev-parse', 'master').stdout.strip()
    path = skill_dir('mdf') / 'assets/ci/review.py'
    spec = importlib.util.spec_from_file_location('ci_initial_release', path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    def invoke(repo, backend, prompt, body, schema, prefix):
        ctx = body['context']
        if 'reviewers' not in body:
            return {'id': prefix.name, 'rules_sha256': ctx['rules_sha256'], 'paths': body['assigned_paths'],
                    'findings': [], 'incomplete': [], 'previous_findings': []}
        result = {k: ctx[k] for k in
                  ('source', 'delivery_base', 'review_base', 'review_head', 'policy_ref', 'rules_sha256', 'context_sha256')}
        result.update(schema_version=3, decision='pass', incomplete=[], adjudications=[], reviewers=body['reviewers'])
        return result
    monkeypatch.setattr(runner, 'invoke', invoke)
    args = SimpleNamespace(repo=str(work), source='release/1.2.1', head='HEAD', policy_ref=policy,
                           review_base=policy, previous_report=None, backend='codex', output_dir=str(tmp_path / 'ci'))
    assert runner.run(args) == 0


def test_rewritten_backmerge_stops_without_creating_new_merge(python_exe, tmp_path, monkeypatch):
    _, remote, work, _, record, _ = waiting_backmerge(python_exe, tmp_path, monkeypatch)
    back = Path(record['worktree'])
    original = git(remote, 'rev-parse', 'develop').stdout
    git(back, 'checkout', '--detach', record['base'])
    git(back, 'branch', '-f', record['source'], record['base'])
    git(back, 'checkout', record['source'])
    failed = mdf(python_exe, 'finish-gitflow', '--repo', str(work))
    assert failed.returncode != 0 and 'pull_state_changed' in failed.stderr
    assert git(back, 'rev-parse', 'HEAD').stdout.strip() == record['base']
    assert git(remote, 'rev-parse', 'develop').stdout == original


def test_first_release_incremental_round_keeps_fixed_base_and_old_blockers(python_exe, tmp_path, monkeypatch):
    from mdf_core.reviewing.context import context
    repo, _, work, _ = prepare(python_exe, tmp_path, monkeypatch, 'release')
    path = repo / '.mdf/manifest.yaml'
    path.write_text(re.sub(r'(?m)^  latest_release:.*$', '  latest_release: null', path.read_text()))
    commit(repo)
    git(work, 'merge', '--no-ff', '--no-edit', 'master')
    completed_materials(work)
    policy = git(repo, 'rev-parse', 'master').stdout.strip()
    initial = context(work, 'release/1.2.1', 'HEAD', policy, policy)
    count = initial['roster']['reviewers']
    _, _, finding = incremental_report()
    previous = {k: initial[k] for k in ('source', 'delivery_base', 'review_base', 'review_head',
                                       'policy_ref', 'rules_sha256', 'context_sha256')}
    previous.update(schema_version=3, decision='changes_requested', incomplete=[], reviewers=[
        {'id': f'r{i + 1}', 'rules_sha256': initial['rules_sha256'], 'paths': initial['paths'][i::count],
         'findings': [finding] if i == 0 else [], 'incomplete': [], 'previous_findings': []}
        for i in range(count)], adjudications=[{
            'id': finding['id'], 'decision': 'accepted', 'reason': '已确认的旧阻断项',
            'evidence': ['src/service.py:1'], 'needs_reproduction': False}])
    for round_number in range(2):
        (work / 'src/service.py').write_text(f'changed = {round_number}\n')
        commit(work)
        current = context(work, initial['source'], 'HEAD', policy, previous['review_head'], previous)
        assert current['round'] == 'incremental'
        assert current['delivery_base'] == initial['delivery_base']
        report = {k: current[k] for k in ('source', 'delivery_base', 'review_base', 'review_head',
                                         'policy_ref', 'rules_sha256', 'context_sha256')}
        report.update(schema_version=3, decision='pass', incomplete=[], adjudications=[], reviewers=[
            {'id': f'r{i + 1}', 'rules_sha256': current['rules_sha256'], 'paths': current['paths'][i::count],
             'findings': [], 'incomplete': [], 'previous_findings': [
                 {'id': finding['id'], 'state': 'reopened', 'evidence': '旧问题仍然存在'}]}
            for i in range(count)])
        with pytest.raises(MDFError):
            validate(current, report)
        report['reviewers'][0]['findings'] = [finding]
        report['adjudications'] = previous['adjudications']
        report['decision'] = 'changes_requested'
        assert validate(current, report)['decision'] == 'changes_requested'
        previous = report
