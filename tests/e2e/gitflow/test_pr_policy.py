"""白名单历史检查、同步 merge 和 push 审计。"""
import json

import pytest

from mdf_test_support import git, mdf, payload
from support_delivery import commit, local_repo, attach_origin


def configured_repo(tmp_path):
    repo = local_repo(tmp_path)
    manifest = repo / '.mdf/manifest.yaml'
    manifest.write_text(manifest.read_text() + '\ncloseout:\n  mode: pr\n  provider: gitlab\n')
    commit(repo)
    git(repo, 'branch', '-f', 'develop', 'master')
    git(repo, 'checkout', 'develop')
    return repo


@pytest.mark.parametrize('path', ['.mdf/config.json', '.agents/tool.py', '.cursor/other.py', '.kiro/config', 'AGENTS.md'])
def test_develop_maintenance_audit_is_path_based(python_exe, tmp_path, path):
    repo = configured_repo(tmp_path)
    before = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    dest = repo / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text('维护\n')
    commit(repo)
    result = payload(mdf(python_exe, 'audit-push', '--repo', str(repo), '--branch', 'develop',
                         '--before', before, '--after', 'HEAD'))['result']
    assert result['verdict'] == 'pass'


def test_planning_code_revert_cannot_hide_in_final_diff(python_exe, tmp_path):
    repo = configured_repo(tmp_path)
    git(repo, 'checkout', '-b', 'planning')
    original = (repo / 'src/service.py').read_text()
    (repo / 'src/service.py').write_text('changed = True\n')
    commit(repo)
    (repo / 'src/service.py').write_text(original)
    (repo / 'docs/new.md').write_text('文档\n')
    commit(repo)
    git(repo, 'checkout', 'develop')
    failed = mdf(python_exe, 'planning', 'land', '--repo', str(repo))
    assert failed.returncode != 0 and 'pr_required' in failed.stderr


def test_planning_sync_merge_does_not_count_existing_develop_code(python_exe, tmp_path):
    repo = configured_repo(tmp_path)
    planning = tmp_path / 'planning'
    git(repo, 'worktree', 'add', '-b', 'planning', str(planning))
    (planning / 'docs/new.md').write_text('文档\n')
    commit(planning)
    (repo / 'src/service.py').write_text('develop_change = True\n')
    commit(repo)
    git(planning, 'merge', '--no-ff', '--no-edit', 'develop')
    result = payload(mdf(python_exe, 'planning', 'land', '--repo', str(repo)))
    assert result['landed']
    assert len(git(repo, 'show', '-s', '--format=%P', 'HEAD').stdout.split()) == 2


def test_generic_merge_blocks_unapproved_delivery(python_exe, tmp_path):
    repo = configured_repo(tmp_path)
    git(repo, 'checkout', '-b', 'feature/code')
    (repo / 'src/service.py').write_text('feature = True\n')
    commit(repo)
    git(repo, 'checkout', 'develop')
    assert 'pr_required' in mdf(python_exe, 'merge-no-ff', '--repo', str(repo), '--commit', 'feature/code').stderr


def test_bulk_push_checks_every_landing_and_platform_proof(python_exe, tmp_path):
    repo = configured_repo(tmp_path)
    before = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    git(repo, 'checkout', '-b', 'feature/code')
    (repo / 'src/service.py').write_text('feature = True\n')
    commit(repo)
    head = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    git(repo, 'checkout', 'develop')
    git(repo, 'merge', '--no-ff', '--no-edit', 'feature/code')
    merged = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    proof = tmp_path / 'proof.json'
    proof.write_text(json.dumps({'pull_requests': [{'id': 1, 'url': 'https://example.invalid/pull/1',
        'state': 'merged', 'source': 'feature/code', 'target': 'develop', 'head': head, 'merge_commit': merged}]}))
    args = ['audit-push', '--repo', str(repo), '--branch', 'develop', '--before', before, '--after', 'HEAD']
    assert payload(mdf(python_exe, *args))['result']['verdict'] == 'needs-review'
    assert payload(mdf(python_exe, *args, '--evidence-file', str(proof)))['result']['verdict'] == 'pass'
    (repo / 'src/unapproved.py').write_text('unapproved = True\n')
    commit(repo)
    assert payload(mdf(python_exe, *args, '--evidence-file', str(proof)))['result']['verdict'] == 'violation'


def test_audit_uses_before_policy_even_when_after_disables_mode(python_exe, tmp_path):
    repo = configured_repo(tmp_path)
    before = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    path = repo / '.mdf/manifest.yaml'
    path.write_text(path.read_text().replace('mode: pr', 'mode: local'))
    (repo / 'src/service.py').write_text('unexpected = True\n')
    commit(repo)
    result = payload(mdf(python_exe, 'audit-push', '--repo', str(repo), '--branch', 'develop',
                         '--before', before, '--after', 'HEAD'))['result']
    assert result['verdict'] == 'violation'


def test_sync_rejects_unapproved_ahead_before_any_push(python_exe, tmp_path):
    repo = configured_repo(tmp_path)
    git(repo, 'branch', 'planning')
    remote = attach_origin(repo, tmp_path)
    (repo / 'src/service.py').write_text('unexpected = True\n')
    commit(repo)
    before = git(remote, 'show-ref').stdout
    preview = payload(mdf(python_exe, 'sync', '--repo', str(repo)))
    result = mdf(python_exe, 'sync', '--repo', str(repo), '--confirm', preview['confirmation'])
    assert result.returncode != 0 and 'pr_required' in result.stderr
    assert git(remote, 'show-ref').stdout == before


def test_sync_can_atomically_push_valid_planning_and_develop(python_exe, tmp_path):
    repo = configured_repo(tmp_path)
    git(repo, 'branch', 'planning')
    remote = attach_origin(repo, tmp_path)
    git(repo, 'checkout', 'planning')
    (repo / 'docs/new.md').write_text('规划文档\n')
    commit(repo)
    git(repo, 'checkout', 'develop')
    payload(mdf(python_exe, 'planning', 'land', '--repo', str(repo)))
    preview = payload(mdf(python_exe, 'sync', '--repo', str(repo)))
    result = payload(mdf(python_exe, 'sync', '--repo', str(repo), '--confirm', preview['confirmation']))
    assert result['trunks']['develop']['push'] == 'updated'
    assert git(repo, 'rev-parse', 'develop').stdout == git(remote, 'rev-parse', 'develop').stdout


def test_sync_cannot_disable_mode_to_push_unapproved_code(python_exe, tmp_path):
    repo = configured_repo(tmp_path)
    git(repo, 'branch', 'planning')
    remote = attach_origin(repo, tmp_path)
    path = repo / '.mdf/manifest.yaml'
    path.write_text(path.read_text().replace('mode: pr', 'mode: local'))
    (repo / 'src/service.py').write_text('unapproved = True\n')
    commit(repo)
    before = git(remote, 'show-ref').stdout
    preview = payload(mdf(python_exe, 'sync', '--repo', str(repo)))
    failed = mdf(python_exe, 'sync', '--repo', str(repo), '--confirm', preview['confirmation'])
    assert failed.returncode != 0 and 'pr_required' in failed.stderr
    assert git(remote, 'show-ref').stdout == before


def test_planning_document_conflict_resolution_is_checked_as_documents(python_exe, tmp_path):
    from _support import run
    repo = configured_repo(tmp_path)
    (repo / 'docs/topic.md').write_text('共同起点\n')
    commit(repo)
    work = tmp_path / 'planning'
    git(repo, 'worktree', 'add', '-b', 'planning', str(work))
    (work / 'docs/topic.md').write_text('规划文档\n')
    commit(work)
    (repo / 'docs/topic.md').write_text('develop 文档\n')
    commit(repo)
    failed = run(['git', 'merge', '--no-ff', '--no-edit', 'develop'], cwd=work)
    assert failed.returncode != 0
    (work / 'docs/topic.md').write_text('规划文档与 develop 文档\n')
    commit(work)
    result = payload(mdf(python_exe, 'planning', 'land', '--repo', str(repo)))
    assert result['landed']
