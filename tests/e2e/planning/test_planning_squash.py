"""planning land 在所有模式下检查未共享尾段，并保留共享历史。"""
import json

import pytest

from mdf_test_support import copy_fixture, init_git, checkout_develop, planning_worktree, git, mdf, payload
from squash_execute import execute
from mdf_core.workspace import squash
from mdf_core.foundation.errors import MDFError


def prepare(python_exe, tmp_path, mode):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "master")
    checkout_develop(repo)
    if mode == 'pr':
        manifest = repo / '.mdf/manifest.yaml'
        manifest.write_text(manifest.read_text() + '\ncloseout:\n  mode: pr\n  provider: github\n')
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'test: 启用 PR mode')
        git(repo, 'branch', '-f', 'master', 'develop')
    work = planning_worktree(python_exe, repo)
    return repo, work


def note(work, text):
    (work / 'notes.md').write_text(text)
    git(work, 'add', '.')
    git(work, 'commit', '-m', 'docs: 规划记录')


@pytest.mark.parametrize('mode', ['local', 'pr'])
@pytest.mark.parametrize('keep_all', [False, True])
def test_planning_land_requires_analysis_and_resumes(python_exe, tmp_path, mode, keep_all):
    repo, work = prepare(python_exe, tmp_path, mode)
    note(work, '草稿\n')
    first = git(work, 'rev-parse', 'HEAD').stdout.strip()
    note(work, '定稿\n')
    before = {b: git(repo, 'rev-parse', b).stdout for b in ('develop', 'planning')}
    tree = git(work, 'rev-parse', 'HEAD^{tree}').stdout
    failed = mdf(python_exe, 'planning', 'land', '--repo', str(work))
    assert failed.returncode != 0
    error = json.loads(failed.stderr.strip().splitlines()[-1])
    assert error['error'] == 'squash_required'
    assert {b: git(repo, 'rev-parse', b).stdout for b in before} == before
    body = error['details']
    body.update(start_commit=body['floor'], segments=[{'tip': body['old_tip'], 'message': 'docs: 完成规划'}])
    if keep_all:
        body['segments'].insert(0, {'tip': first, 'message': 'docs: 独立规划草稿'})
        body['noop_reason'] = '两次独立规划决策均保留'
    result = execute(work.resolve(), body, False, [])
    assert result['tree_equal'] and git(work, 'rev-parse', 'HEAD^{tree}').stdout == tree
    assert execute(work.resolve(), body, True, [])['start_is_ancestor']
    assert payload(mdf(python_exe, 'planning', 'land', '--repo', str(work)))['landed']
    assert git(repo, 'show', 'develop:notes.md').stdout == '定稿\n'
    assert git(work, 'status', '--porcelain').stdout == ''
    note(work, '补充一\n')
    note(work, '补充二\n')
    failed = mdf(python_exe, 'planning', 'land', '--repo', str(work))
    assert failed.returncode != 0 and 'squash_required' in failed.stderr


@pytest.mark.parametrize('boundary', ['remote', 'tag', 'branch'])
def test_planning_squash_only_rewrites_new_tail(python_exe, tmp_path, boundary):
    repo, work = prepare(python_exe, tmp_path, 'local')
    note(work, '共享规划\n')
    shared = git(work, 'rev-parse', 'HEAD').stdout.strip()
    if boundary == 'remote':
        remote = tmp_path / 'remote.git'
        git(tmp_path, 'init', '--bare', str(remote))
        git(repo, 'remote', 'add', 'origin', str(remote))
        git(work, 'push', 'origin', 'planning')
    elif boundary == 'tag':
        git(work, 'tag', 'planning-shared')
    else:
        git(work, 'branch', 'dependent')
    note(work, '临时\n')
    note(work, '完成\n')
    body = squash.check(work)
    assert body['floor'] == shared
    body.update(start_commit=body['floor'], segments=[{'tip': body['old_tip'], 'message': 'docs: 补充规划'}])
    execute(work.resolve(), body, False, [])
    git(work, 'merge-base', '--is-ancestor', shared, 'HEAD')
    assert payload(mdf(python_exe, 'planning', 'land', '--repo', str(work)))['landed']


def test_planning_squash_cannot_hide_code_revert_in_pr_mode(python_exe, tmp_path):
    repo, work = prepare(python_exe, tmp_path, 'pr')
    source = work / 'src/service.py'
    original = source.read_text()
    source.write_text('unapproved = True\n')
    git(work, 'add', '.')
    git(work, 'commit', '-m', 'test: 代码改动')
    source.write_text(original)
    note(work, '规划\n')
    before = git(work, 'rev-parse', 'HEAD').stdout
    with pytest.raises(MDFError, match='完整文档历史检查'):
        squash.check(work)
    failed = mdf(python_exe, 'planning', 'land', '--repo', str(work))
    assert failed.returncode != 0 and 'pr_required' in failed.stderr
    assert git(work, 'rev-parse', 'HEAD').stdout == before


def test_dirty_planning_is_preserved_before_land(python_exe, tmp_path):
    repo, work = prepare(python_exe, tmp_path, 'local')
    note(work, '提交\n')
    (work / 'notes.md').write_text('未提交\n')
    before = git(repo, 'rev-parse', 'develop').stdout
    failed = mdf(python_exe, 'planning', 'land', '--repo', str(work))
    assert failed.returncode != 0 and 'dirty_worktree' in failed.stderr
    assert git(repo, 'rev-parse', 'develop').stdout == before
    assert (work / 'notes.md').read_text() == '未提交\n'
