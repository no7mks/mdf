"""against 工作区内容、当前规则、只读身份和直接历史比较。"""
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


@pytest.mark.parametrize('kind', ['code', 'fact'])
def test_against_includes_staged_unstaged_untracked_and_current_filters(tmp_path, kind):
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
    ctx = context(repo, against=base) if kind == 'code' else fact_context(repo, base)
    assert ctx['paths'] == ['src/new.py', 'src/service.py', 'src/staged.py']
    assert '+working = 2' in ctx['diff'] and '+staged_only = 1' in ctx['diff'] and '+untracked = 1' in ctx['diff']
    assert '+staged = 1' not in ctx['diff'] and 'generated = 1' not in ctx['diff']
    assert before == {p.relative_to(repo): p.read_bytes() for p in repo.rglob('*') if p.is_file()}


def test_against_untracked_content_change_invalidates_report(tmp_path):
    repo, base = repository(tmp_path)
    path = repo / 'src/new.py'
    path.write_text('value = 1\n')
    first = context(repo, against=base)
    report = passing(first)
    assert validate(first, report)['decision'] == 'pass'
    path.write_text('value = 2\n')
    second = context(repo, against=base)
    assert first['worktree_sha256'] != second['worktree_sha256']
    with pytest.raises(MDFError):
        validate(second, report)


@pytest.mark.parametrize('kind', ['code', 'fact'])
def test_against_current_sourceset_expansion_and_narrowing(tmp_path, kind):
    repo, base = repository(tmp_path)
    config = repo / '.mdf/modules.yaml'
    original = config.read_text()
    extra = repo / 'outside.py'
    extra.write_text('outside = 1\n')
    build = lambda: context(repo, against=base) if kind == 'code' else fact_context(repo, base)
    assert 'outside.py' not in build()['paths']
    config.write_text(original.replace('"src/**"', '"src/**"\n      - "outside.py"', 1))
    assert 'outside.py' in build()['paths']
    config.write_text(original)
    assert 'outside.py' not in build()['paths']


@pytest.mark.parametrize('command', ['review-context', 'fact-audit'])
def test_against_cli_requires_one_comparison_mode(python_exe, tmp_path, command):
    repo, _ = repository(tmp_path)
    extra = ['--head', 'HEAD'] if command == 'review-context' else ['--scope', 'full']
    result = mdf(python_exe, command, '--repo', str(repo), '--against', 'HEAD', *extra)
    assert result.returncode != 0 and 'invalid_arguments' in result.stderr


def test_against_tracks_ignored_tracked_file_and_file_to_directory_change(tmp_path):
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
    ctx = context(repo, against=base)
    assert ctx['paths'] == ['src/old', 'src/old/new.py', 'src/service.py']
    assert '+new = True' in ctx['diff'] and '+tracked = True' in ctx['diff']
