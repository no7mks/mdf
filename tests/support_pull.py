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

    def find(self, source, target, *, head=None):
        return next((deepcopy(p) for p in self.pulls if p['source'] == source and p['target'] == target
                     and (head is None or p['state'] == 'open' or p['head'] == head)), None)

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


def prepare(python_exe, tmp_path, monkeypatch, kind='hotfix', *, hotfix_name=None):
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
    if hotfix_name is not None:
        arguments += ['--name', hotfix_name]
    if kind == 'adhoc':
        arguments = ['--name', 'service-health', '--work', '更新说明']
    else:
        obj = write_release_objectives(tmp_path) if kind == 'release' else write_work_objectives(tmp_path)
        arguments += ['--objectives-file', str(obj)]
    result = payload(mdf(python_exe, 'start', '--repo', str(repo), '--kind', kind, *arguments))
    work = Path(result['worktree'])
    if kind in {'hotfix', 'release'}:
        write_changelog_release(work, '1.2.1')
        (work / 'src/service.py').write_text('fixed = True\n')
    else:
        root = work / 'changes/unreleased/service-health'
        proposals = '[]' if kind == 'adhoc' else '[prp-0001]'
        (root / 'CHANGE.md').write_text(
            f'---\nchange_kind: {kind}\nsource_branch: {kind}/service-health\nproposals: {proposals}\n---\n')
        if kind == 'adhoc':
            obj = root / 'objectives.md'
            obj.write_text(obj.read_text().replace('[ ]', '[x]'))
    commit(work)
    pull_finish.preflight(work, git(work, "branch", "--show-current").stdout.strip())
    squash_pending(work)
    return repo, remote, work, platform


def squash_pending(work):
    """平台测试先完成新增的提交前整理，再测试平台生命周期。"""
    from mdf_core.workspace.squash import check
    from squash_execute import execute
    plan = check(work)
    if not plan['noop']:
        plan.update(start_commit=plan['floor'], segments=[
            {'tip': plan['old_tip'], 'message': 'test: 整理交付准备'}])
        execute(work.resolve(), plan, False, [])
