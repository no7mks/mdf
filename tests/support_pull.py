"""PR mode 的离线平台和真实 Git 远端。"""
from copy import deepcopy
from pathlib import Path

from mdf_test_support import git, mdf, payload, write_release_objectives, write_work_objectives
from support_delivery import commit, start_repo, write_changelog_release


class Platform:
    def __init__(self):
        self.pulls = []

    def get(self, number):
        item = self.pulls[number - 1]
        if item['state'] == 'open':
            item['head'] = git(self.remote, 'rev-parse', item['source']).stdout.strip()
        return deepcopy(self.pulls[number - 1])

    def find(self, source, target):
        return next((deepcopy(p) for p in self.pulls if p['source'] == source and p['target'] == target), None)

    def create(self, source, target, title, description):
        head = git(self.repo, 'rev-parse', source).stdout.strip()
        result = {'id': len(self.pulls) + 1, 'url': 'https://forge.invalid/project/pull/1',
                  'source': source, 'target': target, 'head': head, 'state': 'open', 'merge_commit': None}
        self.pulls.append(result)
        return deepcopy(result)

    def merge(self, number, tmp_path):
        pull = self.pulls[number - 1]
        work = tmp_path / f'platform-{number}'
        git(tmp_path, 'clone', '--branch', pull['target'], str(self.remote), str(work))
        git(work, 'merge', '--no-ff', '--no-edit', 'origin/' + pull['source'])
        git(work, 'push', 'origin', pull['target'])
        pull.update(state='merged', merge_commit=git(work, 'rev-parse', 'HEAD').stdout.strip())
        return pull['merge_commit']


def prepare(python_exe, tmp_path, monkeypatch, kind='hotfix'):
    repo, remote = start_repo(tmp_path)
    manifest = repo / '.mdf/manifest.yaml'
    manifest.write_text(manifest.read_text() + '\ncloseout:\n  mode: pr\n  provider: github\n')
    commit(repo)
    git(repo, 'branch', '-f', 'develop', 'master')
    git(repo, 'push', 'origin', 'master', 'develop')
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    from mdf_core.lifecycle import pull_finish
    identity = {'provider': 'github', 'host': 'forge.invalid', 'project': 'team/project', 'origin': str(remote)}
    monkeypatch.setattr(pull_finish, 'origin', lambda *_: identity)
    monkeypatch.setattr(pull_finish, 'Forge', lambda *_: platform)
    arguments = ['--proposal', 'prp-0001', '--roster', 'solo'] if kind == 'feature' else ['--version', '1.2.1']
    obj = write_release_objectives(tmp_path) if kind == 'release' else write_work_objectives(tmp_path)
    result = payload(mdf(python_exe, 'start', '--repo', str(repo), '--kind', kind,
                         '--objectives-file', str(obj), *arguments))
    work = Path(result['worktree'])
    if kind in {'hotfix', 'release'}:
        write_changelog_release(work, '1.2.1')
        (work / 'src/service.py').write_text('fixed = True\n')
    else:
        root = work / 'changes/unreleased/service-health'
        (root / 'CHANGE.md').write_text('---\nchange_kind: feature\nsource_branch: feature/service-health\nproposals: [prp-0001]\n---\n')
    commit(work)
    return repo, remote, work, platform
