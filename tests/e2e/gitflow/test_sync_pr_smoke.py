"""sync PR 的精简主路径；完整恢复与竞态矩阵留在 release。"""
import pytest

from mdf_test_support import git, payload
from support_sync import prepare, sync


@pytest.mark.parametrize('branch,provider,diverged', [
    ('master', 'github', False),
])
def test_sync_pr_waits_merges_and_continues(python_exe, tmp_path, monkeypatch, branch, provider, diverged):
    repo, remote, platform = prepare(tmp_path, monkeypatch, provider, (branch,), diverged)
    original = git(repo, 'rev-parse', branch).stdout
    waiting = payload(sync(python_exe, repo))
    assert waiting['status'] == 'waiting_for_pr' and not waiting['completed']
    assert git(repo, 'rev-parse', branch).stdout == original
    assert payload(sync(python_exe, repo))['status'] == 'waiting_for_pr'
    assert len(platform.pulls) == 1
    merged = platform.merge(1, tmp_path)
    assert payload(sync(python_exe, repo))['status'] == 'ready_to_sync'
    assert git(repo, 'rev-parse', branch).stdout.strip() == merged
    done = payload(sync(python_exe, repo, pr=False))
    assert done['trunks'][branch]['pull'] == 'noop' and done['trunks'][branch]['push'] == 'noop'
    assert git(remote, 'rev-parse', branch).stdout.strip() == merged
    assert git(repo, 'status', '--porcelain').stdout == ''
