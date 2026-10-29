"""报告前轻量复核：输入变化拒绝旧结论，不重复执行完整 audit。"""
import json
from types import SimpleNamespace

import pytest

from mdf_test_support import git, mdf, payload
from mdf_core.foundation.errors import MDFError
from mdf_core.reviewing import fact_context as context_module, fact_identity, worktree
from mdf_core.reviewing.fact_report import command_fact_report_check
from test_commit_fact_audit import commit, repository, report_for


def report_files(tmp_path, ctx):
    context_file, report_file = tmp_path / 'context.json', tmp_path / 'report.json'
    context_file.write_text(json.dumps(ctx))
    report_file.write_text(json.dumps(report_for(ctx)))
    return str(context_file), str(report_file)


def test_report_check_reuses_context_without_snapshot_or_audit(tmp_path, monkeypatch, capsys):
    repo, base = repository(tmp_path)
    ctx = context_module.fact_context(repo, base)
    context_file, report_file = report_files(tmp_path, ctx)

    def forbidden(*args, **kwargs):
        pytest.fail('轻量复核不得创建 snapshot 或重跑 audit')

    monkeypatch.setattr(context_module, 'fact_context', forbidden)
    monkeypatch.setattr(context_module, 'audit_payload', forbidden)
    monkeypatch.setattr(worktree, 'initialize', forbidden)
    before = {p.relative_to(repo): p.read_bytes() for p in repo.rglob('*') if p.is_file()}
    command_fact_report_check(SimpleNamespace(repo=str(repo), context_file=context_file, report_file=report_file))
    result = json.loads(capsys.readouterr().out)
    assert result['result']['decision'] == 'pass'
    assert before == {p.relative_to(repo): p.read_bytes() for p in repo.rglob('*') if p.is_file()}


@pytest.mark.parametrize('change', ['content', 'mode', 'delete', 'rename', 'untracked', 'staged',
                                   'manifest', 'modules', 'agents', 'head', 'shallow'])
def test_report_cli_rejects_changed_inputs(python_exe, tmp_path, change):
    repo, base = repository(tmp_path)
    ctx = context_module.fact_context(repo, base)
    context_file, report_file = report_files(tmp_path, ctx)
    source = repo / 'src/service.py'
    if change == 'content':
        source.write_text('changed = True\n')
    elif change == 'mode':
        source.chmod(0o755)
    elif change == 'delete':
        source.unlink()
    elif change == 'rename':
        source.rename(source.with_name('renamed.py'))
    elif change == 'untracked':
        source.with_name('new.py').write_text('new = True\n')
    elif change == 'staged':
        source.write_text('changed = True\n')
        git(repo, 'add', '.')
    elif change in {'manifest', 'modules', 'agents'}:
        name = {'manifest': '.mdf/manifest.yaml', 'modules': '.mdf/modules.yaml', 'agents': 'AGENTS.md'}[change]
        path = repo / name
        path.write_text(path.read_text() + '\n# changed\n')
    elif change == 'head':
        git(repo, 'commit', '--allow-empty', '-m', 'test: 仅更新历史')
    else:
        (repo / '.git/shallow').write_text(base + '\n')
    result = mdf(python_exe, 'fact-audit-report-check', '--repo', str(repo),
                 '--context-file', context_file, '--report-file', report_file)
    assert result.returncode != 0
    assert '须重新生成 context 并审阅' in result.stderr


@pytest.mark.parametrize('area', ['scripts', 'references', 'assets'])
def test_report_check_rejects_changed_mdf_files(tmp_path, monkeypatch, area):
    repo, base = repository(tmp_path)
    tool_root = tmp_path / 'installed'
    path = tool_root / area / ('tool.py' if area == 'scripts' else 'contract.json')
    path.parent.mkdir(parents=True)
    path.write_text('first')
    original = fact_identity.tool_manifest
    monkeypatch.setattr(fact_identity, 'tool_manifest', lambda root: original(tool_root))
    ctx = context_module.fact_context(repo, base)
    path.write_text('changed')
    with pytest.raises(MDFError, match='输入身份已变化'):
        fact_identity.check_fact_inputs(repo, ctx)


def test_report_check_uses_fixed_against_and_ignores_excluded_files(python_exe, tmp_path):
    repo, base = repository(tmp_path)
    (repo / '.gitignore').write_text('ignored.txt\n')
    git(repo, 'branch', 'review-base', base)
    ctx = context_module.fact_context(repo, 'review-base')
    context_file, report_file = report_files(tmp_path, ctx)
    (repo / 'ignored.txt').write_text('not an input')
    # 改动符号 ref 不改变原 against 或 HEAD。
    other = git(repo, 'commit-tree', f'{base}^{{tree}}', '-p', base, '-m', 'test: 移动 ref').stdout.strip()
    git(repo, 'branch', '-f', 'review-base', other)
    result = payload(mdf(python_exe, 'fact-audit-report-check', '--repo', str(repo),
                         '--context-file', context_file, '--report-file', report_file))
    assert result['result']['against'] == base
    assert result['result']['decision'] == 'pass'
    assert not (repo / '.mdf/logs').exists()


@pytest.mark.parametrize('kind', ['commit', 'blob'])
@pytest.mark.parametrize('ref_base', ['refs/replace/', 'refs/custom-replace/'])
def test_fact_review_ignores_replacement_objects(tmp_path, monkeypatch, kind, ref_base):
    repo, base = repository(tmp_path)
    doc = repo / 'docs/system/interfaces/api.md'
    doc.write_text(doc.read_text().replace('path: src/service.py', 'path: src'))
    replacement = commit(repo)
    original = base
    if kind == 'blob':
        original = git(repo, 'rev-parse', f'{base}:docs/system/interfaces/api.md').stdout.strip()
        replacement = git(repo, 'rev-parse', f'{replacement}:docs/system/interfaces/api.md').stdout.strip()
    git(repo, 'checkout', '--detach', base)
    ctx = context_module.fact_context(repo, base)
    monkeypatch.setenv('GIT_REPLACE_REF_BASE', ref_base)
    git(repo, 'replace', original, replacement)
    fact_identity.check_fact_inputs(repo, ctx)
    refreshed = context_module.fact_context(repo, base)
    assert refreshed['base_mappings'] == ctx['base_mappings']
    assert refreshed['context_sha256'] == ctx['context_sha256']
