"""PR 提交前必须分析并 squash；复用原 PR 且不改写已发布 head。"""
from mdf_test_support import git, mdf, payload
from support_delivery import commit
from support_pull import prepare, squash_pending


def test_push_blocks_unanalyzed_commits_then_accepts_squash(python_exe, tmp_path, monkeypatch):
    _, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    for number in range(2):
        (work / 'src/service.py').write_text(f'value = {number}\n')
        commit(work)
    before = git(remote, 'show-ref').stdout
    failed = mdf(python_exe, 'pr', '--repo', str(work))
    assert failed.returncode != 0 and 'squash_required' in failed.stderr
    assert git(remote, 'show-ref').stdout == before and platform.pulls == []
    squash_pending(work)
    first = payload(mdf(python_exe, 'pr', '--repo', str(work)))
    published = first['pull_request']['head']
    for number in range(2, 4):
        (work / 'src/service.py').write_text(f'value = {number}\n')
        commit(work)
    failed = mdf(python_exe, 'pr', '--repo', str(work))
    assert failed.returncode != 0 and 'squash_required' in failed.stderr
    assert git(remote, 'rev-parse', first['source']).stdout.strip() == published
    squash_pending(work)
    git(work, 'merge-base', '--is-ancestor', published, 'HEAD')
    updated = payload(mdf(python_exe, 'pr', '--repo', str(work)))
    assert len(platform.pulls) == 1
    assert updated['pull_request']['head'] != published
    assert git(remote, 'rev-list', '--count', f'{published}..{first["source"]}').stdout.strip() == '1'
