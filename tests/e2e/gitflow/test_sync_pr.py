"""受保护 trunk 的 sync PR 生命周期与保留现场。"""
import json

import pytest

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle import pull_finish
from mdf_core.lifecycle.publish import state_path
from mdf_core.workspace import sync_pull
from mdf_test_support import git, mdf, payload
from support_delivery import commit, start_repo
from support_pull import Platform


def prepare(tmp_path, monkeypatch, provider='github', branches=('master',), diverged=False):
    repo, remote = start_repo(tmp_path)
    manifest = repo / '.mdf/manifest.yaml'
    manifest.write_text(manifest.read_text() + f'\ncloseout:\n  mode: pr\n  provider: {provider}\n')
    commit(repo)
    git(repo, 'branch', '-f', 'develop', 'master')
    git(repo, 'branch', 'planning', 'master')
    git(repo, 'push', 'origin', 'master', 'develop', 'planning')
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    identity = {'provider': provider, 'host': 'forge.invalid', 'project': 'team/project', 'origin': str(remote)}
    monkeypatch.setattr(sync_pull, 'origin', lambda *_: identity)
    monkeypatch.setattr(sync_pull, 'Forge', lambda *_: platform)
    for branch in branches:
        git(repo, 'checkout', branch)
        (repo / f'{branch}-local.txt').write_text('本地工作\n')
        commit(repo)
        if diverged:
            other = tmp_path / f'other-{branch}'
            git(tmp_path, 'clone', '--branch', branch, str(remote), str(other))
            (other / f'{branch}-remote.txt').write_text('远端工作\n')
            commit(other)
            git(other, 'push')
    return repo, remote, platform


def sync(python_exe, repo, pr=True):
    args = ['sync', '--repo', str(repo)] + (['--pr'] if pr else [])
    preview = payload(mdf(python_exe, *args))
    return mdf(python_exe, *args, '--confirm', preview['confirmation'])


@pytest.mark.parametrize('provider', ['github', 'gitlab'])
@pytest.mark.parametrize('branch', ['master', 'develop'])
@pytest.mark.parametrize('diverged', [False, True])
def test_sync_pr_merges_then_ff_and_continues(python_exe, tmp_path, monkeypatch, provider, branch, diverged):
    repo, remote, platform = prepare(tmp_path, monkeypatch, provider, (branch,), diverged)
    local = git(repo, 'rev-parse', branch).stdout.strip()
    before = git(remote, 'show-ref').stdout
    preview = payload(mdf(python_exe, 'sync', '--repo', str(repo), '--pr'))
    assert preview['pull_plan'][branch]['action'] == 'create_pr'
    assert not platform.pulls and git(remote, 'show-ref').stdout == before
    first = payload(sync(python_exe, repo))
    assert first['status'] == 'waiting_for_pr' and not first['completed']
    source = first['pull_requests'][branch]['source']
    assert git(remote, 'rev-parse', source).stdout.strip() == local
    assert git(repo, 'rev-parse', branch).stdout.strip() == local
    assert payload(sync(python_exe, repo))['status'] == 'waiting_for_pr'
    assert len(platform.pulls) == 1
    merged = platform.merge(1, tmp_path)
    ready = payload(sync(python_exe, repo))
    assert ready['status'] == 'ready_to_sync'
    assert git(repo, 'rev-parse', branch).stdout.strip() == merged
    assert git(repo, 'rev-parse', source).stdout.strip() == local
    result = payload(sync(python_exe, repo, pr=False))
    assert result['trunks'][branch] == {**result['trunks'][branch], 'pull': 'noop', 'push': 'noop'}
    assert git(repo, 'status', '--porcelain').stdout == ''


def test_both_trunks_wait_without_syncing_other_work(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = prepare(tmp_path, monkeypatch, branches=('master', 'develop'))
    git(repo, 'checkout', 'planning')
    (repo / 'docs/plan.md').write_text('规划\n')
    commit(repo)
    before = git(remote, 'rev-parse', 'planning').stdout
    result = payload(sync(python_exe, repo))
    assert set(result['pull_requests']) == {'master', 'develop'}
    assert len(platform.pulls) == 2 and git(remote, 'rev-parse', 'planning').stdout == before
    platform.merge(1, tmp_path)
    assert payload(sync(python_exe, repo))['status'] == 'waiting_for_pr'
    platform.merge(2, tmp_path)
    assert payload(sync(python_exe, repo))['status'] == 'ready_to_sync'
    assert payload(sync(python_exe, repo))['trunks']['planning']['push'] == 'updated'


@pytest.mark.parametrize('boundary', ['record', 'push', 'create', 'ff', 'completed'])
def test_sync_pr_resumes_interrupted_operations(python_exe, tmp_path, monkeypatch, boundary):
    repo, _, platform = prepare(tmp_path, monkeypatch)
    if boundary in {'ff', 'completed'}:
        payload(sync(python_exe, repo))
        platform.merge(1, tmp_path)
    original_git, original_write, original_create = sync_pull.git, sync_pull.write_json, platform.create
    original_ff = sync_pull.sync_local
    fired = []

    def interrupt_git(repo_path, *args, **kwargs):
        result = original_git(repo_path, *args, **kwargs)
        if boundary == 'push' and args[0] == 'push' and not fired:
            fired.append(True)
            raise MDFError('模拟 push 响应丢失', code='test_interrupted')
        return result

    def interrupt_write(path, value):
        if not fired and ((boundary == 'completed' and value.get('completed'))
                          or (boundary == 'record' and not value.get('pull'))):
            original_write(path, value)
            fired.append(True)
            raise MDFError('模拟落盘后中断', code='test_interrupted')
        return original_write(path, value)

    def interrupt_create(*args):
        original_create(*args)
        fired.append(True)
        raise MDFError('模拟 create 响应丢失', code='test_interrupted')

    def interrupt_ff(*args):
        original_ff(*args)
        fired.append(True)
        raise MDFError('模拟 ff 后中断', code='test_interrupted')

    with monkeypatch.context() as patch:
        patch.setattr(sync_pull, 'git', interrupt_git)
        patch.setattr(sync_pull, 'write_json', interrupt_write)
        if boundary == 'create':
            patch.setattr(platform, 'create', interrupt_create)
        if boundary == 'ff':
            patch.setattr(sync_pull, 'sync_local', interrupt_ff)
        assert sync(python_exe, repo).returncode != 0
    assert fired
    result = payload(sync(python_exe, repo))
    assert len(platform.pulls) == 1
    if boundary not in {'ff', 'completed'}:
        assert result['status'] == 'waiting_for_pr'
        platform.merge(1, tmp_path)
        result = payload(sync(python_exe, repo))
    if boundary != 'completed':
        assert result['status'] == 'ready_to_sync'
    assert payload(sync(python_exe, repo))['trunks']['master']['push'] == 'noop'


@pytest.mark.parametrize('change', ['local_commit', 'dirty', 'source', 'pull_head', 'target', 'closed', 'squash'])
def test_sync_pr_preserves_unexpected_changes(python_exe, tmp_path, monkeypatch, change):
    repo, remote, platform = prepare(tmp_path, monkeypatch)
    first = payload(sync(python_exe, repo))
    source = first['pull_requests']['master']['source']
    if change == 'local_commit':
        (repo / 'later.txt').write_text('后续工作\n')
        commit(repo)
    elif change == 'dirty':
        (repo / 'dirty.txt').write_text('未提交\n')
    elif change == 'source':
        git(repo, 'branch', '-f', source, 'planning')
    elif change == 'pull_head':
        git(remote, 'update-ref', 'refs/heads/' + source, 'planning')
    elif change == 'target':
        platform.pulls[0]['target'] = 'develop'
    elif change == 'closed':
        platform.pulls[0]['state'] = 'closed'
    elif change == 'squash':
        pull = platform.pulls[0]
        work = tmp_path / 'squash'
        git(tmp_path, 'clone', '--branch', 'master', str(remote), str(work))
        git(work, 'merge', '--squash', 'origin/' + source)
        commit(work)
        git(work, 'push')
        pull.update(state='merged', merge_commit=git(work, 'rev-parse', 'HEAD').stdout.strip())
    local = git(repo, 'rev-parse', 'master').stdout
    before = git(remote, 'show-ref').stdout
    result = sync(python_exe, repo)
    if change == 'closed':
        assert payload(result)['pull_requests']['master']['status'] == 'closed_without_merge'
    else:
        assert result.returncode != 0
    assert git(repo, 'rev-parse', 'master').stdout == local
    assert git(remote, 'show-ref').stdout == before and len(platform.pulls) == 1


def test_pr_option_and_record_are_bound_to_confirmation(python_exe, tmp_path, monkeypatch):
    repo, _, platform = prepare(tmp_path, monkeypatch)
    preview = payload(mdf(python_exe, 'sync', '--repo', str(repo)))
    result = mdf(python_exe, 'sync', '--repo', str(repo), '--pr', '--confirm', preview['confirmation'])
    assert result.returncode != 0 and 'sync_plan_changed' in result.stderr
    assert not platform.pulls
    payload(sync(python_exe, repo))
    preview = payload(mdf(python_exe, 'sync', '--repo', str(repo), '--pr'))
    path = state_path(repo, 'sync/master')
    record = json.loads(path.read_text())
    record['pull']['id'] = 999
    path.write_text(json.dumps(record))
    result = mdf(python_exe, 'sync', '--repo', str(repo), '--pr', '--confirm', preview['confirmation'])
    assert result.returncode != 0 and 'sync_plan_changed' in result.stderr


def test_sync_lock_blocks_concurrent_closeout_and_sync(python_exe, tmp_path, monkeypatch):
    repo, _, platform = prepare(tmp_path, monkeypatch)
    with pull_finish.finish_lock(repo):
        result = mdf(python_exe, 'sync', '--repo', str(repo), '--pr')
    assert result.returncode != 0 and 'finish_busy' in result.stderr
    assert not platform.pulls


@pytest.mark.parametrize('branch', ['master', 'develop'])
def test_sync_pr_conflict_resolution_updates_original_pr(python_exe, tmp_path, monkeypatch, branch):
    repo, remote, platform = prepare(tmp_path, monkeypatch, branches=(branch,))
    (repo / 'src/service.py').write_text('local = True\n')
    commit(repo)
    other = tmp_path / 'remote-conflict'
    git(tmp_path, 'clone', '--branch', branch, str(remote), str(other))
    (other / 'src/service.py').write_text('remote = True\n')
    commit(other)
    git(other, 'push')
    first = payload(sync(python_exe, repo))
    source = first['pull_requests'][branch]['source']
    original_head = git(repo, 'rev-parse', branch).stdout.strip()
    work = tmp_path / 'resolution'
    git(repo, 'worktree', 'add', str(work), source)
    from _support import run
    failed = run(['git', 'merge', '--no-ff', '--no-edit', f'origin/{branch}'], cwd=work)
    assert failed.returncode != 0
    (work / 'src/service.py').write_text('local = True\nremote = True\n')
    commit(work)
    result = payload(sync(python_exe, repo))
    assert result['status'] == 'waiting_for_pr' and len(platform.pulls) == 1
    assert platform.pulls[0]['head'] == git(work, 'rev-parse', 'HEAD').stdout.strip()
    assert git(repo, 'rev-parse', branch).stdout.strip() == original_head
    platform.merge(1, tmp_path)
    assert payload(sync(python_exe, repo))['status'] == 'ready_to_sync'
    assert (repo / 'src/service.py').read_text() == 'local = True\nremote = True\n'


def test_sync_pr_requires_new_confirmation_if_target_advances_during_recovery(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = prepare(tmp_path, monkeypatch)
    payload(sync(python_exe, repo))
    platform.merge(1, tmp_path)
    original_get = platform.get
    advanced = []

    def get_and_advance(number):
        if not advanced:
            advanced.append(True)
            work = tmp_path / 'platform-1'
            (work / 'later.txt').write_text('确认后的新提交\n')
            commit(work)
            git(work, 'push')
        return original_get(number)

    local = git(repo, 'rev-parse', 'master').stdout
    monkeypatch.setattr(platform, 'get', get_and_advance)
    result = sync(python_exe, repo)
    assert result.returncode != 0 and 'sync_plan_changed' in result.stderr
    assert git(repo, 'rev-parse', 'master').stdout == local
    assert payload(sync(python_exe, repo))['status'] == 'ready_to_sync'


@pytest.mark.parametrize('boundary', ['record', 'push'])
@pytest.mark.parametrize('continued_work', [False, True])
def test_sync_pr_source_update_resumes_without_duplicate_pr(
        python_exe, tmp_path, monkeypatch, boundary, continued_work):
    repo, remote, platform = prepare(tmp_path, monkeypatch)
    first = payload(sync(python_exe, repo))
    source = first['pull_requests']['master']['source']
    old = git(repo, 'rev-parse', source).stdout.strip()
    new = git(repo, 'commit-tree', old + '^{tree}', '-p', old, '-m', 'test: PR 返工提交').stdout.strip()
    git(repo, 'update-ref', 'refs/heads/' + source, new, old)
    original_write, original_git = sync_pull.write_json, sync_pull.git
    fired = []

    def interrupt_write(path, value):
        original_write(path, value)
        if boundary == 'record' and value.get('previous_head') and not fired:
            fired.append(True)
            raise MDFError('模拟更新记录后中断', code='test_interrupted')

    def interrupt_git(repo_path, *args, **kwargs):
        result = original_git(repo_path, *args, **kwargs)
        if boundary == 'push' and args[0] == 'push' and not fired:
            fired.append(True)
            raise MDFError('模拟更新 push 响应丢失', code='test_interrupted')
        return result

    with monkeypatch.context() as patch:
        patch.setattr(sync_pull, 'write_json', interrupt_write)
        patch.setattr(sync_pull, 'git', interrupt_git)
        assert sync(python_exe, repo).returncode != 0
    assert fired
    if continued_work:
        newer = git(repo, 'commit-tree', new + '^{tree}', '-p', new, '-m', 'test: 继续 PR 返工').stdout.strip()
        git(repo, 'update-ref', 'refs/heads/' + source, newer, new)
        new = newer
    assert payload(sync(python_exe, repo))['status'] == 'waiting_for_pr'
    assert len(platform.pulls) == 1 and platform.pulls[0]['head'] == new
    assert git(repo, 'rev-parse', 'master').stdout.strip() == old
    assert git(remote, 'rev-parse', source).stdout.strip() == new
    platform.merge(1, tmp_path)
    assert payload(sync(python_exe, repo))['status'] == 'ready_to_sync'


def test_sync_pr_rejects_rewritten_target_even_with_platform_merge(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = prepare(tmp_path, monkeypatch)
    payload(sync(python_exe, repo))
    state = json.loads(state_path(repo, 'sync/master').read_text())
    git(remote, 'update-ref', 'refs/heads/master', state['base'] + '^')
    platform.merge(1, tmp_path)
    local = git(repo, 'rev-parse', 'master').stdout
    result = sync(python_exe, repo)
    assert result.returncode != 0 and '目标分支历史已改写' in result.stderr
    assert git(repo, 'rev-parse', 'master').stdout == local
