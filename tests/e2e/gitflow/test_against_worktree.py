"""against：code-review 要求 clean HEAD；fact-audit 仍比较完整工作区。"""
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


def test_fact_against_includes_staged_unstaged_untracked_and_current_filters(tmp_path):
    repo, base = repository(tmp_path)
    (repo / 'src/service.py').write_text('staged = 1\n')
    git(repo, 'add', 'src/service.py')
    (repo / 'src/service.py').write_text('working = 2\n')
    (repo / 'src/staged.py').write_text('staged_only = 1\n')
    git(repo, 'add', 'src/staged.py')
    (repo / 'src/new.py').write_text('untracked = 1\n')
    (repo / 'src/generated.py').write_text('generated = 1\n')
    (repo / 'src/ignored.py').write_text('git_ignored = 1\n')
    (repo / '.gitignore').write_text('src/ignored.py\n')
    vendor = repo / '.codex/skills/mdf/tool.py'
    vendor.parent.mkdir(parents=True)
    vendor.write_text('vendor = 1\n')
    modules = repo / '.mdf/modules.yaml'
    modules.write_text(modules.read_text().replace('    ignore: []',
        '    ignore:\n      - pattern: src/generated.py\n        reason: generated'))
    before = {p.relative_to(repo): p.read_bytes() for p in repo.rglob('*') if p.is_file()}
    ctx = fact_context(repo, base)
    assert ctx['paths'] == ['src/new.py', 'src/service.py', 'src/staged.py']
    assert '+working = 2' in ctx['diff'] and '+staged_only = 1' in ctx['diff'] and '+untracked = 1' in ctx['diff']
    assert '+staged = 1' not in ctx['diff'] and 'generated = 1' not in ctx['diff']
    assert before == {p.relative_to(repo): p.read_bytes() for p in repo.rglob('*') if p.is_file()}


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


def test_fact_against_untracked_content_change_invalidates_report(tmp_path):
    repo, base = repository(tmp_path)
    path = repo / 'src/new.py'
    path.write_text('value = 1\n')
    first = fact_context(repo, base)
    assert first['worktree_sha256']
    path.write_text('value = 2\n')
    second = fact_context(repo, base)
    assert first['worktree_sha256'] != second['worktree_sha256']


@pytest.mark.parametrize('kind', ['code', 'fact'])
def test_against_current_sourceset_expansion_and_narrowing(tmp_path, kind):
    repo, base = repository(tmp_path)
    config = repo / '.mdf/modules.yaml'
    original = config.read_text()
    extra = repo / 'outside.py'
    extra.write_text('outside = 1\n')
    if kind == 'code':
        git(repo, 'add', '--all')
        git(repo, 'commit', '-m', 'test: 提交 sourceset 探测')
        build = lambda: context(repo, against=base)
    else:
        build = lambda: fact_context(repo, base)
    assert 'outside.py' not in build()['paths']
    config.write_text(original.replace('"src/**"', '"src/**"\n      - "outside.py"', 1))
    if kind == 'code':
        git(repo, 'add', '--all')
        git(repo, 'commit', '-m', 'test: 扩大 sourceset')
    assert 'outside.py' in build()['paths']
    config.write_text(original)
    if kind == 'code':
        git(repo, 'add', '--all')
        git(repo, 'commit', '-m', 'test: 收回 sourceset')
    assert 'outside.py' not in build()['paths']


@pytest.mark.parametrize('command', ['review-context', 'fact-audit'])
def test_against_cli_requires_one_comparison_mode(python_exe, tmp_path, command):
    repo, _ = repository(tmp_path)
    extra = ['--head', 'HEAD'] if command == 'review-context' else ['--scope', 'full']
    result = mdf(python_exe, command, '--repo', str(repo), '--against', 'HEAD', *extra)
    assert result.returncode != 0 and 'invalid_arguments' in result.stderr


def test_fact_against_tracks_ignored_tracked_file_and_file_to_directory_change(tmp_path):
    repo, _ = repository(tmp_path)
    old = repo / 'src/old'
    old.write_text('old file\n')
    (repo / '.gitignore').write_text('src/service.py\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'test: 准备文件替换')
    base = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    old.unlink()
    old.mkdir()
    (old / 'new.py').write_text('new = True\n')
    (repo / 'src/service.py').write_text('tracked = True\n')
    ctx = fact_context(repo, base)
    assert ctx['paths'] == ['src/old', 'src/old/new.py', 'src/service.py']
    assert '+new = True' in ctx['diff'] and '+tracked = True' in ctx['diff']
