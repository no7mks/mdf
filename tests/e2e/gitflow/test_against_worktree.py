"""against：code-review 仍须 clean；fact-audit 比较当前工作区（可 dirty）。"""
import pytest

from mdf_test_support import copy_fixture, git, init_git, mdf, payload
from mdf_core.foundation.errors import MDFError
from mdf_core.reviewing.context import context
from mdf_core.reviewing.fact_context import fact_context
from mdf_core.reviewing.report import validate
from test_ci_review import passing


def repository(tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    return repo, git(repo, 'rev-parse', 'HEAD').stdout.strip()


def test_code_against_rejects_dirty_worktree(tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/service.py').write_text('dirty = 1\n')
    with pytest.raises(MDFError, match='clean|dirty_worktree'):
        context(repo, against=base)


def test_fact_against_includes_dirty_worktree(tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/service.py').write_text('dirty = 1\n')
    ctx = fact_context(repo, base)
    assert ctx['against'] == base and 'src/service.py' in ctx['paths']
    assert '+dirty = 1' in ctx['diff']


def test_code_against_compares_clean_head_to_base(tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/service.py').write_text('updated = 1\n')
    (repo / 'src/new.py').write_text('added = 1\n')
    (repo / 'docs/note.md').write_text('doc only\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 提交审查范围')
    head = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    ctx = context(repo, against=base)
    assert ctx['against'] == base and ctx['head'] == head and ctx['scope'] == 'head'
    assert ctx['paths'] == ['src/new.py', 'src/service.py']
    assert 'docs/note.md' not in ctx['paths']
    assert '+updated = 1' in ctx['diff'] and '+added = 1' in ctx['diff']
    report = passing(ctx)
    assert validate(ctx, report)['decision'] == 'pass'
    assert validate(ctx, report)['head'] == head


def test_fact_against_compares_worktree_to_base(tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/service.py').write_text('updated = 1\n')
    (repo / 'src/new.py').write_text('added = 1\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 提交事实范围')
    ctx = fact_context(repo, base)
    assert ctx['against'] == base and ctx['mode'] == 'against'
    assert 'src/new.py' in ctx['paths'] and 'src/service.py' in ctx['paths']
    assert '+updated = 1' in ctx['diff'] and '+added = 1' in ctx['diff']


def test_code_against_head_change_invalidates_report(tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/service.py').write_text('value = 1\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 第一版')
    first = context(repo, against=base)
    report = passing(first)
    assert validate(first, report)['decision'] == 'pass'
    (repo / 'src/service.py').write_text('value = 2\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 第二版')
    second = context(repo, against=base)
    assert first['head'] != second['head']
    with pytest.raises(MDFError):
        validate(second, report)


def test_fact_against_head_change_updates_fingerprint(tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/new.py').write_text('value = 1\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 第一版')
    first = fact_context(repo, base)
    (repo / 'src/new.py').write_text('value = 2\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 第二版')
    second = fact_context(repo, base)
    assert first['input_identity']['implementation_digest'] != second['input_identity']['implementation_digest']
    assert 'head' not in first['input_identity']
    assert first['worktree_sha256'] != second['worktree_sha256']


@pytest.mark.parametrize('kind', ['code', 'fact'])
def test_against_current_sourceset_expansion_and_narrowing(tmp_path, kind):
    repo, base = repository(tmp_path)
    config = repo / '.mdf/modules.yaml'
    original = config.read_text()
    extra = repo / 'outside.py'
    extra.write_text('outside = 1\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 提交 sourceset 探测')
    build = (lambda: context(repo, against=base)) if kind == 'code' else (lambda: fact_context(repo, base))
    assert 'outside.py' not in build()['paths']
    config.write_text(original.replace('"src/**"', '"src/**"\n      - "outside.py"', 1))
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 扩大 sourceset')
    assert 'outside.py' in build()['paths']
    config.write_text(original)
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 收回 sourceset')
    assert 'outside.py' not in build()['paths']


@pytest.mark.parametrize('command', ['review-context', 'fact-audit'])
def test_against_cli_requires_one_comparison_mode(python_exe, tmp_path, command):
    repo, _ = repository(tmp_path)
    extra = ['--head', 'HEAD'] if command == 'review-context' else ['--scope', 'full']
    result = mdf(python_exe, command, '--repo', str(repo), '--against', 'HEAD', *extra)
    assert result.returncode != 0 and 'invalid_arguments' in result.stderr


def test_fact_against_quick_skips_semantic_flag(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    result = mdf(python_exe, 'fact-audit', '--repo', str(repo), '--against', base, '--quick')
    data = payload(result)
    assert data['semantic_review'] is False and data['mode'] == 'quick'
    assert data['result']['against'] == base and data['result']['mode'] == 'against'


def test_fact_against_tracks_committed_file_to_directory_change(tmp_path):
    repo, _ = repository(tmp_path)
    old = repo / 'src/old'
    old.write_text('old file\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 准备文件替换')
    base = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    old.unlink()
    old.mkdir()
    (old / 'new.py').write_text('new = True\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 文件改目录')
    ctx = fact_context(repo, base)
    assert 'src/old' in ctx['paths'] or 'src/old/new.py' in ctx['paths']
    assert '+new = True' in ctx['diff']
