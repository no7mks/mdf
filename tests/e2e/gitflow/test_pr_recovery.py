"""PR close-out 中断、重入与共享仓库并发恢复。"""
import json
import subprocess

import pytest

from conftest import skill_dir
from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle import pull_finish, pull_publish
from mdf_core.lifecycle.publish import state_path
from mdf_test_support import git, mdf, payload
from support_delivery import commit
from support_pull import prepare


@pytest.mark.parametrize('same_source', [True, False])
def test_concurrent_finish_is_rejected_before_platform_writes(python_exe, tmp_path, monkeypatch, same_source):
    repo, _, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    first = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    original = platform.get
    nested = []
    def interleave(number):
        if not nested:
            nested.append(None)
            source = first['source'] if same_source else 'release/1.2.1'
            nested[0] = mdf(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', source)
        return original(number)
    monkeypatch.setattr(platform, 'get', interleave)
    result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert result['status'] == 'waiting_for_merge'
    assert nested[0].returncode != 0 and 'finish_busy' in nested[0].stderr
    assert len(platform.pulls) == 1


def test_finish_lock_is_shared_across_processes_and_released_after_exit(python_exe, tmp_path, monkeypatch):
    repo, _, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    code = (
        f"import sys; sys.path.insert(0, {str(skill_dir('mdf') / 'scripts')!r})\n"
        "from pathlib import Path\n"
        "from mdf_core.lifecycle.pull_finish import finish_lock\n"
        f"with finish_lock(Path({str(repo)!r})):\n"
        "    print('locked', flush=True)\n"
        "    sys.stdin.read()\n"
    )
    process = subprocess.Popen([python_exe, '-c', code], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'locked'
        busy = mdf(python_exe, 'finish-gitflow', '--repo', str(work))
        assert busy.returncode != 0 and 'finish_busy' in busy.stderr
        assert platform.pulls == []
    finally:
        process.terminate()
        process.communicate(timeout=5)
    result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert result['status'] == 'waiting_for_merge' and len(platform.pulls) == 1


@pytest.mark.parametrize('changed_branch', [False, True])
def test_backmerge_worktree_creation_resumes_after_branch_was_created(python_exe, tmp_path, monkeypatch, changed_branch):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    merged = platform.merge(1, tmp_path)
    def interrupted(repo_path, branch, path, start):
        git(repo_path, 'branch', branch, merged if changed_branch else start)
        raise MDFError('模拟 worktree 创建中断', code='test_interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(pull_publish, 'add_linked_worktree', interrupted)
        assert mdf(python_exe, 'finish-gitflow', '--repo', str(work)).returncode != 0
    resumed = mdf(python_exe, 'finish-gitflow', '--repo', str(work))
    if changed_branch:
        assert resumed.returncode != 0 and 'pull_state_changed' in resumed.stderr
        assert git(repo, 'rev-parse', 'codex/backmerge/1.2.1').stdout.strip() == merged
        return
    result = payload(resumed)
    assert result['completed'] and len(platform.pulls) == 1
    git(remote, 'merge-base', '--is-ancestor', merged, 'develop')


@pytest.mark.parametrize('boundary', ['detach', 'delete', 'completed_record'])
def test_cleanup_interruption_resumes_without_republishing(python_exe, tmp_path, monkeypatch, boundary):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    first = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    platform.merge(1, tmp_path)
    original_git, original_write = pull_finish.git, pull_finish.write_json
    fired = []
    def interrupted_git(repo_path, *args, **kwargs):
        result = original_git(repo_path, *args, **kwargs)
        if not fired and ((boundary == 'detach' and args[:2] == ('checkout', '--detach'))
                          or (boundary == 'delete' and args[:2] == ('update-ref', '-d'))):
            fired.append(True)
            raise MDFError('模拟清理中断', code='test_interrupted')
        return result
    def interrupted_write(path, value):
        if boundary == 'completed_record' and value.get('completed'):
            fired.append(True)
            raise MDFError('模拟 completed 记录中断', code='test_interrupted')
        return original_write(path, value)
    with monkeypatch.context() as patch:
        patch.setattr(pull_finish, 'git', interrupted_git)
        patch.setattr(pull_finish, 'write_json', interrupted_write)
        assert mdf(python_exe, 'finish-gitflow', '--repo', str(work)).returncode != 0
    assert fired
    snapshot = git(remote, 'show-ref').stdout
    done = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', first['source']))
    assert done['completed'] and git(remote, 'show-ref').stdout == snapshot
    assert not git(repo, 'for-each-ref', 'refs/heads/' + first['source']).stdout
    assert json.loads(state_path(repo, first['source']).read_text())['completed']


@pytest.mark.parametrize('recreated', [False, True])
def test_cleanup_preserves_source_changed_by_another_git_process(python_exe, tmp_path, monkeypatch, recreated):
    repo, _, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    first = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    source, head = first['source'], first['pull_request']['head']
    new_head = git(work, 'commit-tree', head + '^{tree}', '-p', head, '-m', 'test: 后续提交').stdout.strip()
    key = f'branch.{source}.mdf-roster'
    before = git(repo, 'config', '--local', '--get', key).stdout
    platform.merge(1, tmp_path)
    original = pull_finish.git
    fired = []
    def advanced(repo_path, *args, **kwargs):
        if not fired and args[:2] in {('branch', '-D'), ('update-ref', '-d')}:
            fired.append(True)
            if recreated:
                result = original(repo_path, *args, **kwargs)
                git(repo, 'update-ref', 'refs/heads/' + source, new_head, '0' * 40)
                return result
            git(repo, 'update-ref', 'refs/heads/' + source, new_head, head)
        return original(repo_path, *args, **kwargs)
    monkeypatch.setattr(pull_finish, 'git', advanced)
    result = mdf(python_exe, 'finish-gitflow', '--repo', str(work))
    assert fired and result.returncode != 0 and 'pull_state_changed' in result.stderr
    assert git(repo, 'rev-parse', source).stdout.strip() == new_head
    assert git(repo, 'config', '--local', '--get', key).stdout == before


def test_cleanup_preserves_source_checked_out_in_another_worktree(python_exe, tmp_path, monkeypatch):
    repo, _, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    first = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    source = first['source']
    platform.merge(1, tmp_path)
    original = pull_finish.git
    other = tmp_path / 'other-owner'
    def occupy(repo_path, *args, **kwargs):
        result = original(repo_path, *args, **kwargs)
        if args[:2] == ('checkout', '--detach'):
            git(repo, 'worktree', 'add', str(other), source)
        return result
    monkeypatch.setattr(pull_finish, 'git', occupy)
    result = mdf(python_exe, 'finish-gitflow', '--repo', str(work))
    assert result.returncode != 0
    assert git(other, 'branch', '--show-current').stdout.strip() == source
    assert git(repo, 'rev-parse', source).stdout.strip() == first['pull_request']['head']
