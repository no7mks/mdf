"""执行 Skill 的最终 Git 清理命令，验证交付事实独立于临时目录。"""
from pathlib import Path

import pytest

from mdf_test_support import git, mdf, payload, run
from support_pull import prepare
from test_adhoc import prepare_finish


def test_local_owner_removal_keeps_delivery_and_long_lived_worktrees(python_exe, tmp_path):
    repo, owner = prepare_finish(python_exe, tmp_path)
    develop, planning, deploy = (repo.parent / branch for branch in ('develop', 'planning', 'deploy'))
    git(repo, 'checkout', 'master')
    git(repo, 'worktree', 'add', str(develop), 'develop')
    git(repo, 'worktree', 'add', '-b', 'planning', str(planning), 'master')
    git(repo, 'worktree', 'add', '--detach', str(deploy), 'master')
    result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(owner)))
    status = payload(mdf(python_exe, 'adhoc-status', '--repo', str(owner), '--slug', 'update-readme'))['result']
    assert result['completed'] and status['completed']
    merged = git(repo, 'rev-parse', 'develop').stdout
    retry = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(develop), '--source', result['source']))
    assert retry['retained_worktree'] == str(owner)
    assert git(develop, 'branch', '--show-current').stdout.strip() == 'develop'
    git(repo, 'worktree', 'remove', result['retained_worktree'])
    assert not owner.exists()
    assert all(path.is_dir() for path in (repo, develop, planning, deploy))
    assert git(repo, 'rev-parse', 'develop').stdout == merged
    assert git(repo, 'show', 'develop:changes/unreleased/update-readme/CHANGE.md').stdout


@pytest.mark.parametrize('dirty', [False, True])
def test_pr_backmerge_then_owner_cleanup_and_recovery(python_exe, tmp_path, monkeypatch, dirty):
    repo, remote, owner, platform = prepare(python_exe, tmp_path, monkeypatch)
    source = payload(mdf(python_exe, 'pr', '--repo', str(owner)))['source']
    platform.merge(1, tmp_path)
    result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(owner)))
    assert result['completed'] and result['remote_deleted']
    back = Path(result['backmerge']['worktree'])
    branch = result['backmerge']['source']
    head = git(back, 'rev-parse', 'HEAD').stdout.strip()
    git(repo, 'merge-base', '--is-ancestor', result['merge_commit'], head)
    git(repo, 'merge-base', '--is-ancestor', head, 'origin/develop')
    before = git(remote, 'show-ref').stdout
    # 恢复结果可能没有 backmerge，按已核实的完整分支从清单定位。
    retry = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', source))
    assert retry['completed']
    trees = git(repo, 'worktree', 'list', '--porcelain').stdout.split('\n\n')
    matches = [entry.splitlines()[0].removeprefix('worktree ') for entry in trees
               if f'branch refs/heads/{branch}' in entry.splitlines()]
    assert matches == [str(back)]
    if dirty:
        (back / 'uncommitted.txt').write_text('保留失败现场\n')
        failed = run(['git', '-C', str(repo), 'worktree', 'remove', str(back)], cwd=repo)
        assert failed.returncode != 0
        assert back.is_dir() and owner.is_dir()
        assert (back / 'uncommitted.txt').read_text() == '保留失败现场\n'
    else:
        git(repo, 'worktree', 'remove', str(back))
        git(repo, 'worktree', 'remove', result['retained_worktree'])
        assert not back.exists() and not owner.exists()
        recovered = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', source))
        assert recovered['completed'] and recovered['retained_worktree'] is None and repo.is_dir()
        git(repo, 'clone', '--no-checkout', str(repo), str(owner))
        git(owner, 'checkout', '--detach', result['pull_request']['head'])
        recovered = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', source))
        assert recovered['completed'] and recovered['retained_worktree'] is None
    assert git(remote, 'show-ref').stdout == before
