"""代码审查按固定 source 的 module 归属过滤；文档不进强制 paths。"""
import pytest

from mdf_test_support import git
from support_delivery import commit
from test_ci_review import ready_context, passing
from mdf_core.reviewing.context import context
from mdf_core.reviewing.report import validate


def review(work, original, explicit):
    if explicit:
        return context(work, against=original['policy_ref'])
    return context(work, original['source'], 'HEAD', original['policy_ref'])


@pytest.mark.parametrize('explicit', [False, True])
@pytest.mark.parametrize('change', ['modify', 'delete', 'move-in', 'move-out'])
def test_review_excludes_unowned_and_ignored_changes(python_exe, tmp_path, monkeypatch, explicit, change):
    _, work, initial = ready_context(python_exe, tmp_path, monkeypatch)
    vendor = work / '.codex/skills/mdf/tool.py'
    vendor.parent.mkdir(parents=True)
    vendor.write_text('vendor = 1\n')
    vendor.with_name('SKILL.md').write_text('# Installed MDF\n')
    project = work / 'src/moved.py'
    if change == 'move-in':
        project.write_text('project = 1\n')
    generated = work / 'src/generated.py'
    generated.write_text('generated = 1\n')
    modules = work / '.mdf/modules.yaml'
    modules.write_text(modules.read_text().replace('    ignore: []',
        '    ignore:\n      - pattern: src/generated.py\n        reason: generated'))
    commit(work)
    if change == 'delete':
        vendor.unlink()
    elif change == 'move-in':
        project.rename(vendor.with_name('new.py'))
    elif change == 'move-out':
        vendor.rename(project)
    else:
        vendor.write_text('vendor = 2\n')
    generated.write_text('generated = 2\n')
    (work / 'src/service.py').write_text('project = 2\n')
    document = work / 'docs/system/interfaces/api.md'
    document.write_text(document.read_text() + '\n项目事实变更。\n')
    commit(work)
    ctx = review(work, initial, explicit)
    assert 'src/service.py' in ctx['paths']
    assert 'docs/system/interfaces/api.md' not in ctx['paths']
    assert 'src/generated.py' not in ctx['paths']
    assert not any(p.startswith('.codex/') for p in ctx['paths'])
    assert '.codex/skills/mdf' not in ctx['diff']
    assert 'generated = ' not in ctx['diff']
    assert ('src/moved.py' in ctx['paths']) == (change == 'move-out')
    assert validate(ctx, passing(ctx))['decision'] == 'pass'


@pytest.mark.parametrize('explicit', [False, True])
@pytest.mark.parametrize('owners', ['outside', 'one', 'all'])
def test_review_uses_source_ownership_and_overlapping_ignore(python_exe, tmp_path, monkeypatch, explicit, owners):
    _, work, initial = ready_context(python_exe, tmp_path, monkeypatch)
    modules = work / '.mdf/modules.yaml'
    module = modules.read_text().split('  default:\n', 1)[1]
    ignored = module.replace('    ignore: []',
        '    ignore:\n      - pattern: src/new.py\n        reason: generated')
    if owners == 'outside':
        config = 'modules:\n  default:\n' + ignored.replace('src/**', 'other/**')
    else:
        config = 'modules:\n  default:\n' + ignored + '  overlapping:\n' + (ignored if owners == 'all' else module)
    modules.write_text(config)
    (work / 'src/new.py').write_text('new = True\n')
    commit(work)
    head = git(work, 'rev-parse', 'HEAD').stdout.strip()
    ctx = review(work, initial, explicit)
    assert ('src/new.py' in ctx['paths']) == (owners == 'one')
    assert ('+new = True' in ctx['diff']) == (owners == 'one')
    assert ctx['rules']['modules' if explicit else 'scope'] == (config if explicit else {'modules': config})
    modules.write_text(config + '\nbudgets:\n  quick: 60\n')
    if explicit:
        from mdf_core.foundation.errors import MDFError
        with pytest.raises(MDFError, match='clean|dirty_worktree'):
            context(work, against=initial['policy_ref'])
        commit(work)
        repeated = context(work, against=initial['policy_ref'])
        assert repeated['paths'] == ctx['paths']
        assert repeated['rules']['modules'] == modules.read_text()
        assert repeated['rules_sha256'] != ctx['rules_sha256']
        assert repeated['head'] != ctx['head']
    else:
        # 当前脏配置不影响固定 source。
        repeated = context(work, initial['source'], head, initial['policy_ref'])
        assert repeated == ctx


@pytest.mark.parametrize('explicit', [False, True])
def test_review_excludes_documents_in_broad_sourceset(python_exe, tmp_path, monkeypatch, explicit):
    _, work, initial = ready_context(python_exe, tmp_path, monkeypatch)
    modules = work / '.mdf/modules.yaml'
    modules.write_text(modules.read_text().replace('"src/**"', '"**"'))
    doc = work / 'docs/system/interfaces/api.md'
    doc.write_text(doc.read_text() + '\n事实修订。\n')
    (work / 'src/service.py').write_text('VALUE = 2\n')
    commit(work)
    ctx = review(work, initial, explicit)
    assert 'src/service.py' in ctx['paths']
    assert not any(p.startswith(('docs/', 'changes/')) for p in ctx['paths'])
    assert '事实修订' not in ctx['diff']
