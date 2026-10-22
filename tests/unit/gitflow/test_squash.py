"""真实 Git 历史验证未共享 squash、分段及动作门禁。"""
import json
from types import SimpleNamespace

import pytest

from mdf_test_support import git
from mdf_core.foundation.errors import MDFError
from mdf_core.workspace import squash
from mdf_core.workspace.git_ops import command_merge_no_ff
from squash_execute import execute


def commit(repo, name, text):
    (repo / name).write_text(text)
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', f'test: {name}')
    return git(repo, 'rev-parse', 'HEAD').stdout.strip()


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / 'repo'
    path.mkdir()
    git(path, 'init', '--initial-branch=master', '--template=')
    (path / '.mdf').mkdir()
    commit(path, '.mdf/manifest.yaml', 'closeout:\n  mode: pr\n  provider: github\n')
    git(path, 'checkout', '-b', 'feature/topic')
    git(path, 'config', 'branch.feature/topic.mdf-start-commit', git(path, 'rev-parse', 'HEAD').stdout.strip())
    return path


def plan(repo, tips=None):
    result = squash.check(repo)
    result.update(start_commit=result['floor'], segments=[
        {'tip': tip, 'message': f'fix: 逻辑改动 {i}'}
        for i, tip in enumerate(tips or [result['old_tip']])])
    return result


def test_multisegment_squash_preserves_tree_and_accepts_analyzed_head(repo):
    for i in range(4):
        tip = commit(repo, 'a', str(i))
        if i == 1:
            middle = tip
    before = git(repo, 'rev-parse', 'HEAD^{tree}').stdout
    result = execute(repo.resolve(), plan(repo, [middle, tip]), False, [])
    assert len(result['commits']) == 2
    assert git(repo, 'rev-parse', 'HEAD^{tree}').stdout == before
    squash.require_ready(repo)
    commit(repo, 'a', 'new')
    with pytest.raises(MDFError, match='分析'):
        squash.require_ready(repo)


def test_noop_with_zero_or_one_candidate(repo):
    assert squash.check(repo)['noop']
    commit(repo, 'a', 'one')
    before = git(repo, 'rev-parse', 'HEAD').stdout
    assert execute(repo.resolve(), plan(repo), False, [])['noop']
    assert git(repo, 'rev-parse', 'HEAD').stdout == before
    squash.require_ready(repo)


def test_analysis_may_keep_independent_commits_without_rewriting(repo):
    one = commit(repo, 'a', 'one')
    two = commit(repo, 'b', 'two')
    body = plan(repo, [one, two])
    body['noop_reason'] = '两个独立改动已各自成段'
    assert execute(repo.resolve(), body, False, [])['noop']
    assert git(repo, 'rev-parse', 'HEAD').stdout.strip() == two
    squash.require_ready(repo)


@pytest.mark.parametrize('boundary', ['branch', 'tag', 'worktree', 'remote', 'finish'])
def test_shared_tip_is_protected(repo, tmp_path, boundary):
    shared = commit(repo, 'a', 'shared')
    if boundary == 'branch':
        git(repo, 'branch', 'dependent')
    elif boundary == 'tag':
        git(repo, 'tag', 'shared')
    elif boundary == 'worktree':
        git(repo, 'worktree', 'add', '--detach', str(tmp_path / 'other'), shared)
    elif boundary == 'remote':
        remote = tmp_path / 'remote.git'
        git(tmp_path, 'init', '--bare', str(remote))
        git(repo, 'remote', 'add', 'origin', str(remote))
        git(repo, 'push', 'origin', 'HEAD:refs/heads/feature/topic')
        git(repo, 'update-ref', '-d', 'refs/remotes/origin/feature/topic')
    else:
        path = squash.common_dir(repo) / 'mdf/finish/feature/topic.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'source': 'feature/topic', 'pending_head': shared}))
    commit(repo, 'a', 'next')
    commit(repo, 'a', 'last')
    body = plan(repo)
    assert body['floor'] == shared
    execute(repo.resolve(), body, False, [])
    git(repo, 'merge-base', '--is-ancestor', shared, 'HEAD')


def test_merge_is_preserved_and_plan_crossing_it_is_rejected(repo):
    start = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    commit(repo, 'a', 'owner')
    git(repo, 'checkout', 'master')
    commit(repo, 'b', 'trunk')
    git(repo, 'checkout', 'feature/topic')
    git(repo, 'merge', '--no-ff', '--no-edit', 'master')
    merged = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    parents = git(repo, 'show', '-s', '--format=%P', merged).stdout
    commit(repo, 'a', 'next')
    commit(repo, 'a', 'last')
    body = plan(repo)
    assert body['floor'] == merged
    bad = {**body, 'floor': start, 'start_commit': start}
    with pytest.raises(ValueError):
        execute(repo.resolve(), bad, False, [])
    execute(repo.resolve(), body, False, [])
    git(repo, 'merge-base', '--is-ancestor', merged, 'HEAD')
    assert git(repo, 'show', '-s', '--format=%P', merged).stdout == parents


def test_role_branch_without_delivery_json_can_squash(repo):
    git(repo, 'checkout', '-b', 'qa/feature/topic')
    commit(repo, 'a', 'test draft')
    commit(repo, 'a', 'test final')
    assert len(execute(repo.resolve(), plan(repo), False, [])['commits']) == 1


def test_merge_entry_blocks_before_any_merge_until_analysis(repo):
    commit(repo, 'a', 'one')
    commit(repo, 'a', 'two')
    before = git(repo, 'rev-parse', 'HEAD').stdout
    with pytest.raises(MDFError) as error:
        command_merge_no_ff(SimpleNamespace(repo=str(repo), commit='master'))
    assert error.value.code == 'squash_required'
    assert git(repo, 'rev-parse', 'HEAD').stdout == before
    execute(repo.resolve(), plan(repo), False, [])
    command_merge_no_ff(SimpleNamespace(repo=str(repo), commit='master'))


def test_dirty_or_active_merge_is_not_a_noop(repo):
    commit(repo, 'a', 'one')
    (repo / 'a').write_text('dirty')
    with pytest.raises(MDFError):
        squash.check(repo)


def test_remote_fetch_failure_does_not_authorize_rewrite(repo, tmp_path):
    commit(repo, 'a', 'one')
    commit(repo, 'a', 'two')
    git(repo, 'remote', 'add', 'origin', str(tmp_path / 'missing.git'))
    with pytest.raises(MDFError):
        squash.check(repo)


def test_roster_merge_blocks_unanalyzed_role_and_preserves_merge(repo, tmp_path):
    from mdf_core.lifecycle.delivery_git import merge_role
    role = tmp_path / 'qa'
    git(repo, 'worktree', 'add', '-b', 'qa/feature/topic', str(role), 'HEAD')
    commit(role, 'tests.txt', 'draft')
    commit(role, 'tests.txt', 'final')
    before = git(repo, 'rev-parse', 'HEAD').stdout
    with pytest.raises(MDFError) as error:
        merge_role(repo, repo / 'changes/unreleased/topic', 'qa/feature/topic')
    assert error.value.code == 'squash_required'
    assert git(repo, 'rev-parse', 'HEAD').stdout == before
    result = execute(role.resolve(), plan(role), False, [])
    merge_role(repo, repo / 'changes/unreleased/topic', 'qa/feature/topic')
    parents = git(repo, 'show', '-s', '--format=%P', 'HEAD').stdout.split()
    assert len(parents) == 2 and parents[1] == result['head']


def test_other_author_lifts_floor(repo):
    commit(repo, 'a', 'one')
    (repo / 'a').write_text('shared author')
    git(repo, 'add', '.')
    git(repo, 'commit', '--author=Other <other@example.invalid>', '-m', 'fix: 他人改动')
    boundary = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    commit(repo, 'a', 'three')
    commit(repo, 'a', 'four')
    body = plan(repo)
    assert body['floor'] == boundary
    execute(repo.resolve(), body, False, [])
    git(repo, 'merge-base', '--is-ancestor', boundary, 'HEAD')


@pytest.mark.parametrize('source_form', ['branch', 'ref', 'sha'])
def test_generic_merge_checks_incoming_role_before_sharing(repo, tmp_path, source_form):
    role = tmp_path / 'qa'
    git(repo, 'worktree', 'add', '-b', 'qa/feature/topic', str(role), 'HEAD')
    commit(role, 'tests.txt', 'draft')
    tip = commit(role, 'tests.txt', 'final')
    source = {'branch': 'qa/feature/topic', 'ref': 'refs/heads/qa/feature/topic', 'sha': tip}[source_form]
    before = git(repo, 'rev-parse', 'HEAD').stdout
    with pytest.raises(MDFError) as error:
        command_merge_no_ff(SimpleNamespace(repo=str(repo), commit=source))
    assert error.value.code == 'squash_required'
    assert git(repo, 'rev-parse', 'HEAD').stdout == before
    execute(role.resolve(), plan(role), False, [])
    command_merge_no_ff(SimpleNamespace(repo=str(repo), commit='qa/feature/topic'))
    parents = git(repo, 'show', '-s', '--format=%P', 'HEAD').stdout.split()
    assert len(parents) == 2


def test_empty_commits_can_pass_analyzed_keep_all_noop(repo):
    tips = []
    for number in range(2):
        git(repo, 'commit', '--allow-empty', '-m', f'ci: 触发检查 {number}')
        tips.append(git(repo, 'rev-parse', 'HEAD').stdout.strip())
    with pytest.raises(MDFError) as error:
        squash.require_ready(repo)
    assert error.value.code == 'squash_required'
    body = plan(repo, tips)
    body['noop_reason'] = '两次独立 CI 触发记录均需保留'
    assert execute(repo.resolve(), body, False, [])['noop']
    assert git(repo, 'rev-parse', 'HEAD').stdout.strip() == tips[-1]
    squash.require_ready(repo)
