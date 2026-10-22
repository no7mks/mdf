"""PR/MR 等待、固定发布提交和部分成功恢复。"""
import json

import pytest

from mdf_test_support import PRP_NAME, git, mdf, payload
from support_delivery import commit
from support_pull import prepare


@pytest.mark.parametrize('kind', ['feature', 'release', 'hotfix'])
def test_pr_finish_waits_then_resumes_idempotently(python_exe, tmp_path, monkeypatch, kind):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, kind)
    before = git(remote, 'show-ref').stdout
    first = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert not first['completed'] and first['status'] == 'waiting_for_merge'
    assert work.is_dir() and git(work, 'branch', '--show-current').stdout.strip() == first['source']
    assert git(work, 'branch', '--show-current').stdout.strip()
    assert git(remote, 'rev-parse', 'master').stdout.strip() in before
    assert not git(remote, 'for-each-ref', 'refs/tags/v1.2.1').stdout
    payload(mdf(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', first['source']))
    assert len(platform.pulls) == 1
    if kind == 'feature':
        assert 'status: ready' in git(repo, 'show', f'origin/develop:docs/proposals/{PRP_NAME}').stdout
        from mdf_core.foundation.yamlutil import read_frontmatter
        assert read_frontmatter(work / 'docs/proposals' / PRP_NAME)[0]['status'] == 'implemented'
    merged = platform.merge(1, tmp_path)
    result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', first['source']))
    assert result['completed'] and result['merge_commit'] == merged
    assert not git(work, 'branch', '--show-current').stdout.strip()
    assert not git(repo, 'for-each-ref', 'refs/heads/' + first['source']).stdout
    if kind != 'feature':
        assert git(remote, 'rev-parse', 'v1.2.1^{}').stdout.strip() == merged
        git(remote, 'merge-base', '--is-ancestor', merged, 'develop')
    snapshot = git(remote, 'show-ref').stdout
    assert payload(mdf(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', first['source']))['completed']
    assert git(remote, 'show-ref').stdout == snapshot


def test_closed_pull_and_changed_merge_never_publish(python_exe, tmp_path, monkeypatch):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    platform.pulls[0]['state'] = 'closed'
    result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert not result['completed'] and result['status'] == 'closed_without_merge'
    assert work.is_dir() and git(work, 'branch', '--show-current').stdout.strip() == result['source']
    platform.pulls[0].update(state='merged', merge_commit=git(repo, 'rev-parse', 'master').stdout.strip())
    failed = mdf(python_exe, 'finish-gitflow', '--repo', str(work))
    assert failed.returncode != 0 and 'invalid_pull_merge' in failed.stderr
    assert not git(remote, 'for-each-ref', 'refs/tags').stdout


def test_creation_response_loss_recovers_same_pull(python_exe, tmp_path, monkeypatch):
    from mdf_core.foundation.errors import MDFError
    repo, _, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    original = platform.create
    def lost(*args):
        original(*args)
        raise MDFError('创建响应丢失', code='test_lost')
    monkeypatch.setattr(platform, 'create', lost)
    assert mdf(python_exe, 'finish-gitflow', '--repo', str(work)).returncode != 0
    monkeypatch.setattr(platform, 'create', original)
    result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert result['status'] == 'waiting_for_merge' and len(platform.pulls) == 1


def test_publish_keeps_tag_on_fixed_merge_after_master_advances(python_exe, tmp_path, monkeypatch):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    merged = platform.merge(1, tmp_path)
    other = tmp_path / 'platform-1'
    (other / 'later.txt').write_text('后来的发布\n')
    commit(other)
    git(other, 'push', 'origin', 'master')
    result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert result['completed']
    assert git(remote, 'rev-parse', 'v1.2.1^{}').stdout.strip() == merged
    assert git(remote, 'ls-tree', '-r', '--name-only', 'develop', 'later.txt').stdout == ''


def test_backmerge_conflict_stays_off_develop_and_resumes_directly(python_exe, tmp_path, monkeypatch):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    git(repo, 'checkout', 'develop')
    (repo / 'src/service.py').write_text('future = True\n')
    commit(repo)
    git(repo, 'push', 'origin', 'develop')
    before = git(remote, 'rev-parse', 'develop').stdout
    payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    platform.merge(1, tmp_path)
    result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert result['status'] == 'published_pending_backmerge' and not result['completed']
    assert work.is_dir() and git(work, 'branch', '--show-current').stdout.strip() == result['source']
    assert git(remote, 'rev-parse', 'develop').stdout == before
    from pathlib import Path
    back = Path(result['backmerge']['worktree'])
    (back / 'src/service.py').write_text('future = True\nfixed = True\n')
    commit(back)
    completed = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert completed['completed']
    assert len(platform.pulls) == 1
    assert git(remote, 'show', 'develop:src/service.py').stdout == 'future = True\nfixed = True\n'


def test_source_updates_reuse_existing_feature_pull(python_exe, tmp_path, monkeypatch):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, 'feature')
    first = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    (work / 'src/service.py').write_text('fixed_after_review = True\n')
    commit(work)
    updated = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert updated['pull_request']['head'] != first['pull_request']['head']
    assert len(platform.pulls) == 1
    platform.merge(1, tmp_path)
    assert payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))['completed']



@pytest.mark.parametrize('kind', ['release', 'hotfix'])
def test_release_candidate_updates_original_pull_and_verification(python_exe, tmp_path, monkeypatch, kind):
    from mdf_core.lifecycle.delivery_state import locate
    from mdf_core.execution.project_verify import evidence_path, associated_suites
    _, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, kind)
    root = work / 'changes' / '1.2.1'
    git(work, 'mv', 'changes/unreleased/1.2.1', 'changes/1.2.1')
    manifest = work / '.mdf/manifest.yaml'
    manifest.write_text(manifest.read_text().replace('latest_release: "1.2.0"', 'latest_release: "1.2.1"'))
    (root / 'suites.json').write_text(json.dumps({'suites': ['billing']}))
    commit(work)
    first = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    (work / 'src/service.py').write_text('fixed_after_review = True\n')
    commit(work)
    assert locate(work)[0] == root
    assert associated_suites(work, '1.2.1') == ['billing']
    payload(mdf(python_exe, 'verify', '--scope', 'branch', '--repo', str(work)))
    assert evidence_path(work) == root / 'verification-report.json'
    evidence = json.loads((root / 'verification-report.json').read_text())
    assert evidence['all_passed'] and ('release' if kind == 'release' else 'smoke') in evidence['suites']
    assert not (work / 'changes/unreleased/1.2.1').exists()
    commit(work)
    updated = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert updated['status'] == 'waiting_for_merge'
    assert updated['pull_request']['head'] != first['pull_request']['head']
    assert len(platform.pulls) == 1
    assert not git(remote, 'for-each-ref', 'refs/tags/v1.2.1').stdout
    merged = platform.merge(1, tmp_path)
    assert payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))['completed']
    assert git(remote, 'rev-parse', 'v1.2.1^{}').stdout.strip() == merged
    assert git(remote, 'show', 'master:src/service.py').stdout == 'fixed_after_review = True\n'


@pytest.mark.parametrize('kind', ['release', 'hotfix'])
def test_release_candidate_updates_still_reject_rewritten_history(python_exe, tmp_path, monkeypatch, kind):
    _, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, kind)
    first = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    git(work, 'reset', '--hard', 'HEAD^')
    failed = mdf(python_exe, 'finish-gitflow', '--repo', str(work))
    assert failed.returncode != 0 and 'pull_state_changed' in failed.stderr
    assert git(remote, 'rev-parse', first['source']).stdout.strip() == first['pull_request']['head']
    assert len(platform.pulls) == 1



@pytest.mark.parametrize('kind', ['feature', 'release', 'hotfix'])
@pytest.mark.parametrize('accepted', [False, True])
def test_pull_update_response_loss_keeps_confirmed_and_pending_heads(python_exe, tmp_path, monkeypatch, kind, accepted):
    from mdf_core.foundation.errors import MDFError
    from mdf_core.lifecycle import pull_finish
    from mdf_core.lifecycle.publish import state_path
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, kind)
    first = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    (work / 'src/service.py').write_text('review_fix = True\n')
    commit(work)
    candidate = git(work, 'rev-parse', 'HEAD').stdout.strip()
    original = pull_finish.git
    def interrupted(repo_path, *args, **kwargs):
        if args[0] == 'push' and any(a.endswith(':refs/heads/' + first['source']) for a in args):
            if accepted:
                original(repo_path, *args, **kwargs)
            platform.get(1)
            platform.merge(1, tmp_path)
            raise MDFError('模拟 push 响应丢失', code='test_lost')
        return original(repo_path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(pull_finish, 'git', interrupted)
        failed = mdf(python_exe, 'finish-gitflow', '--repo', str(work))
        assert failed.returncode != 0
    state = json.loads(state_path(work, first['source']).read_text())
    assert state['head'] == first['pull_request']['head']
    assert state['pending_head'] == candidate
    result = mdf(python_exe, 'finish-gitflow', '--repo', str(work))
    if accepted:
        assert payload(result)['completed']
        assert git(remote, 'show', ('develop' if kind == 'feature' else 'master') + ':src/service.py').stdout == 'review_fix = True\n'
    else:
        assert result.returncode != 0 and 'pull_state_changed' in result.stderr
        assert not git(remote, 'for-each-ref', 'refs/tags/v1.2.1').stdout
    assert len(platform.pulls) == 1


@pytest.mark.parametrize('kind', ['release', 'hotfix'])
@pytest.mark.parametrize('source_action', ['advance', 'dirty'])
def test_merged_release_checks_source_before_publishing(python_exe, tmp_path, monkeypatch, kind, source_action):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, kind)
    first = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    platform.merge(1, tmp_path)
    before = git(remote, 'rev-parse', 'develop').stdout
    (work / 'src/service.py').write_text('late_change = True\n')
    if source_action == 'advance':
        commit(work)
    result = mdf(python_exe, 'finish-gitflow', '--repo', str(repo), '--source', first['source'])
    assert result.returncode != 0
    assert not git(remote, 'for-each-ref', 'refs/tags/v1.2.1').stdout
    assert git(remote, 'rev-parse', 'develop').stdout == before



@pytest.mark.parametrize('invalid', ['branch', 'slug', 'duplicate'])
def test_candidate_material_identity_rejects_mismatch_and_duplicate(python_exe, tmp_path, monkeypatch, invalid):
    from mdf_core.foundation.errors import MDFError
    from mdf_core.lifecycle.delivery_state import locate
    _, _, work, _ = prepare(python_exe, tmp_path, monkeypatch, 'release')
    git(work, 'mv', 'changes/unreleased/1.2.1', 'changes/1.2.1')
    record = work / 'changes/1.2.1/delivery.json'
    if invalid == 'duplicate':
        duplicate = work / 'changes/unreleased/1.2.1/delivery.json'
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text(record.read_text())
    else:
        data = json.loads(record.read_text())
        data[invalid] = 'another-delivery'
        record.write_text(json.dumps(data))
    with pytest.raises(MDFError) as error:
        locate(work)
    assert error.value.code == 'invalid_delivery'


def test_dirty_target_stops_before_tag_and_preserves_source(python_exe, tmp_path, monkeypatch):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    platform.merge(1, tmp_path)
    (repo / 'dirty.txt').write_text('他人未提交的工作\n')
    failed = mdf(python_exe, 'finish-gitflow', '--repo', str(work))
    assert failed.returncode != 0 and 'dirty_worktree' in failed.stderr
    assert (repo / 'dirty.txt').read_text() == '他人未提交的工作\n'
    assert not git(remote, 'for-each-ref', 'refs/tags').stdout
    assert git(work, 'branch', '--show-current').stdout.strip()


def test_tag_push_response_loss_does_not_retag(python_exe, tmp_path, monkeypatch):
    from mdf_core.foundation.errors import MDFError
    from mdf_core.lifecycle import pull_publish
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    platform.merge(1, tmp_path)
    original = pull_publish.git
    def lost(repo, *args, **kwargs):
        result = original(repo, *args, **kwargs)
        if args[0] == 'push' and any('refs/tags/' in item for item in args):
            raise MDFError('tag 响应丢失', code='test_lost')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(pull_publish, 'git', lost)
        assert mdf(python_exe, 'finish-gitflow', '--repo', str(work)).returncode != 0
    tagged = git(remote, 'rev-parse', 'v1.2.1').stdout
    assert payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))['completed']
    assert git(remote, 'rev-parse', 'v1.2.1').stdout == tagged


def test_rejected_develop_push_preserves_pending_without_another_pull(python_exe, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from mdf_core.lifecycle import pull_publish
    repo, _, work, platform = prepare(python_exe, tmp_path, monkeypatch)
    payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    platform.merge(1, tmp_path)
    original = pull_publish.git
    def rejected(repo, *args, **kwargs):
        if args[0] == 'push' and any(item.endswith(':refs/heads/develop') for item in args):
            return SimpleNamespace(returncode=1, stdout='', stderr='protected branch')
        return original(repo, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(pull_publish, 'git', rejected)
        result = payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))
    assert result['status'] == 'published_pending_backmerge'
    assert work.is_dir() and git(work, 'branch', '--show-current').stdout.strip() == result['source']
    assert len(platform.pulls) == 1
    assert result['backmerge']['push_error'] == 'protected branch'
    assert 'pull' not in result['backmerge']
    assert payload(mdf(python_exe, 'finish-gitflow', '--repo', str(work)))['completed']
