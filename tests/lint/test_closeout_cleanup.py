"""收尾清理由 Agent 执行；核对入口共用策略与删除边界。"""
import pytest

from conftest import skill_dir


def workflow(name):
    return (skill_dir('mdf') / 'references' / f'{name}.md').read_text()


def test_cleanup_runs_after_verification_and_preserves_unfinished_work():
    text = workflow('close-out').split('### 工作区清理', 1)[1]
    for rule in (
        '完成核验、Goal 与报告后', '不再单独确认', '不再使用 confidence 策略',
        '主 worktree、planning/deploy worktree', '收口未完成、证据不符、未提交改动或未结束 Git 操作',
        'HEAD 不等于已交付 source tip', '完整 HEAD 未进入远端 develop',
        '用户明确要求保留时遵从', '不扫描删除其他交付',
        '不加 `--force`', '任一删除失败则停止清理', '不重跑 close-out',
        '清理失败不回退已完成交付',
    ):
        assert rule in text
    assert text.index('先完成所有依赖临时目录的读取') < text.index('worktree remove')
    assert text.index('worktree remove') < text.index('结束本对话')
    assert '先删除 backmerge，再删除 owner' in text
    assert '最后一次 tool call' in text and '进程 cwd 必须为主 worktree' in text


def test_cleanup_recovers_only_the_confirmed_delivery_paths():
    text = workflow('close-out').split('### 工作区清理', 1)[1]
    for rule in (
        '`retained_worktree`', 'null 或已移除时跳过', '`backmerge.worktree`',
        '`codex/backmerge/<version>` 查询 worktree 清单', '不得从目录名猜版本',
        '该回合包含本次发布提交', '完整 HEAD 已进入远端 develop',
    ):
        assert rule in text


@pytest.mark.parametrize('name', ['deliver', 'adhoc', 'adhoc-close-out', 'pr-close-out', 'pr'])
def test_all_finish_routes_use_common_cleanup(name):
    text = workflow(name)
    assert 'close-out.md#工作区清理' in text
    assert '默认删除' in text
    for obsolete in ('询问是否删除', '按其 confidence 策略与公共清理规则裁定',
                     '按 confidence 策略决定是否删除', '按原清理授权执行'):
        assert obsolete not in text
