"""sync PR 测试共用的离线平台、仓库与确认调用。"""
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


