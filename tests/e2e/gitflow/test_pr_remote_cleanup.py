"""PR 远端 source 的条件删除、响应丢失和重入保护。"""
from types import SimpleNamespace

import pytest

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle import pull_finish
from mdf_test_support import git, mdf, payload
from mdf_test_support import finish_delivery
from support_delivery import commit
from support_pull import prepare

pytestmark = pytest.mark.release_only


def merged_delivery(python_exe, tmp_path, monkeypatch, kind='hotfix'):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, kind)
    first = payload(mdf(python_exe, 'pr', '--repo', str(work)))
    platform.merge(1, tmp_path)
    return repo, remote, work, first


def remote_source(remote, source):
    return git(remote, 'for-each-ref', '--format=%(objectname)', 'refs/heads/' + source).stdout.strip()


@pytest.mark.parametrize('kind', ['feature', 'release', 'hotfix'])
def test_completed_pr_deletes_only_confirmed_remote_source(python_exe, tmp_path, monkeypatch, kind):
    repo, remote, work, first = merged_delivery(python_exe, tmp_path, monkeypatch, kind)
    result = payload(finish_delivery(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert result['completed'] and result['remote_deleted'] is True
    assert remote_source(remote, first['source']) == ''
    assert remote_source(remote, 'master') and remote_source(remote, 'develop')
    assert work.is_dir() and not git(work, 'branch', '--show-current').stdout.strip()
    snapshot = git(remote, 'show-ref').stdout
    assert payload(finish_delivery(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', first['source']))['completed']
    assert git(remote, 'show-ref').stdout == snapshot


@pytest.mark.parametrize('racing', [False, True])
def test_remote_source_advance_never_deletes_new_tip_or_local_owner(python_exe, tmp_path, monkeypatch, racing):
    repo, remote, work, first = merged_delivery(python_exe, tmp_path, monkeypatch)
    source, head = first['source'], first['pull_request']['head']
    new_head = git(work, 'commit-tree', head + '^{tree}', '-p', head, '-m', 'test: 并发新增提交').stdout.strip()
    original = pull_finish.git
    def advance():
        git(work, 'push', 'origin', f'{new_head}:refs/heads/{source}')
    def interleave(repo_path, *args, **kwargs):
        if args[0] == 'push' and f':refs/heads/{source}' in args:
            assert f'--force-with-lease=refs/heads/{source}:{head}' in args
            advance()
        return original(repo_path, *args, **kwargs)
    if racing:
        monkeypatch.setattr(pull_finish, 'git', interleave)
    else:
        advance()
    result = finish_delivery(python_exe, 'finish-gitflow', '--repo', str(work))
    assert result.returncode != 0 and 'pull_state_changed' in result.stderr
    assert remote_source(remote, source) == new_head
    assert git(work, 'branch', '--show-current').stdout.strip() == source


@pytest.mark.parametrize('outcome', ['nonzero', 'exception'])
def test_remote_delete_response_loss_resumes_from_remote_fact(python_exe, tmp_path, monkeypatch, outcome):
    repo, remote, work, first = merged_delivery(python_exe, tmp_path, monkeypatch)
    source = first['source']
    original_git = pull_finish.git
    attempts = []
    def interrupted(repo_path, *args, **kwargs):
        result = original_git(repo_path, *args, **kwargs)
        if args[0] == 'push' and f':refs/heads/{source}' in args:
            attempts.append(args)
            if outcome == 'exception':
                raise MDFError('模拟删除响应丢失', code='test_lost')
            if outcome == 'nonzero':
                return SimpleNamespace(returncode=1, stdout='', stderr='删除响应丢失')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(pull_finish, 'git', interrupted)
        initial = finish_delivery(python_exe, 'finish-gitflow', '--repo', str(work))
    assert len(attempts) == 1 and remote_source(remote, source) == ''
    if outcome != 'nonzero':
        assert initial.returncode != 0
        assert git(work, 'branch', '--show-current').stdout.strip() == source
    done = payload(finish_delivery(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', source))
    assert done['completed'] and done['remote_deleted'] is True


@pytest.mark.parametrize('completed', [False, True])
def test_confirmed_remote_delete_never_deletes_recreated_source(python_exe, tmp_path, monkeypatch, completed):
    repo, remote, work, first = merged_delivery(python_exe, tmp_path, monkeypatch)
    source, head = first['source'], first['pull_request']['head']
    if completed:
        assert payload(finish_delivery(python_exe, 'finish-gitflow', '--repo', str(work)))['completed']
    else:
        with monkeypatch.context() as patch:
            def interrupted(*args):
                raise MDFError('模拟本地清理前中断', code='test_lost')
            patch.setattr(pull_finish, 'cleanup', interrupted)
            assert finish_delivery(python_exe, 'finish-gitflow', '--repo', str(work)).returncode != 0
    assert remote_source(remote, source) == ''
    new_head = git(repo, 'commit-tree', head + '^{tree}', '-p', head,
                                         '-m', 'test: 新建分支').stdout.strip()
    git(repo, 'push', 'origin', f'{new_head}:refs/heads/{source}')
    result = finish_delivery(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', source)
    assert result.returncode != 0 and 'pull_state_changed' in result.stderr
    assert remote_source(remote, source) == new_head


def test_rejected_delete_can_retry_using_current_ref(python_exe, tmp_path, monkeypatch):
    repo, remote, work, first = merged_delivery(python_exe, tmp_path, monkeypatch)
    source, head = first['source'], first['pull_request']['head']
    original = pull_finish.git

    def rejected(repo_path, *args, **kwargs):
        if args[0] == 'push' and f':refs/heads/{source}' in args:
            return SimpleNamespace(returncode=1, stdout='', stderr='protected branch')
        return original(repo_path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(pull_finish, 'git', rejected)
        failed = finish_delivery(python_exe, 'finish-gitflow', '--repo', str(work))
        assert failed.returncode != 0 and 'remote_cleanup_uncertain' in failed.stderr
    assert remote_source(remote, source) == head
    assert payload(finish_delivery(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', source))['completed']


def test_platform_deleted_source_is_reused_without_another_delete(python_exe, tmp_path, monkeypatch):
    _, remote, work, first = merged_delivery(python_exe, tmp_path, monkeypatch)
    git(work, 'push', 'origin', f":refs/heads/{first['source']}")
    original = pull_finish.git
    def no_delete(repo_path, *args, **kwargs):
        assert not (args[0] == 'push' and f":refs/heads/{first['source']}" in args)
        return original(repo_path, *args, **kwargs)
    monkeypatch.setattr(pull_finish, 'git', no_delete)
    result = payload(finish_delivery(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert result['completed'] and result['remote_deleted'] is True
    assert remote_source(remote, first['source']) == ''


@pytest.mark.parametrize('back_action', ['advance', 'remove'])
@pytest.mark.parametrize('remote_source_deleted', [False, True])
def test_source_cleanup_retry_does_not_republish_backmerge(python_exe, tmp_path, monkeypatch, back_action, remote_source_deleted):
    repo, remote, work, first = merged_delivery(python_exe, tmp_path, monkeypatch, kind='release')
    source, head = first['source'], first['pull_request']['head']
    original = pull_finish.git
    def rejected(repo_path, *args, **kwargs):
        if args[0] == 'push' and f':refs/heads/{source}' in args:
            return SimpleNamespace(returncode=1, stdout='', stderr='protected branch')
        return original(repo_path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(pull_finish, 'git', rejected)
        failed = finish_delivery(python_exe, 'finish-gitflow', '--repo', str(work))
        assert failed.returncode != 0 and 'remote_cleanup_uncertain' in failed.stderr
    assert remote_source(repo, source) == remote_source(remote, source) == head
    from mdf_core.workspace.gitutil import sibling_worktree
    back = sibling_worktree(repo, 'codex/backmerge/1.2.1')
    published = git(remote, 'rev-parse', 'develop').stdout
    assert git(back, 'rev-parse', 'HEAD').stdout == published
    assert git(remote, 'rev-parse', 'develop^2').stdout == git(remote, 'rev-parse', 'master').stdout
    if back_action == 'advance':
        (back / 'later.py').write_text('unrelated = True\n')
        commit(back)
        retained = git(back, 'rev-parse', 'HEAD').stdout
    else:
        git(repo, 'worktree', 'remove', str(back))
    if remote_source_deleted:
        git(repo, 'push', f'--force-with-lease=refs/heads/{source}:{head}', 'origin', f':refs/heads/{source}')

    done = payload(finish_delivery(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', source))
    assert done['completed'] and done['remote_deleted'] and done['deleted'] == source
    assert not remote_source(repo, source) and not remote_source(remote, source)
    assert git(remote, 'rev-parse', 'develop').stdout == published
    if back_action == 'advance':
        assert git(back, 'rev-parse', 'HEAD').stdout == retained
