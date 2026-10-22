"""deliver/next 与 PR close-out 的恢复优先级和返工交接契约。"""
import pytest

from conftest import skill_dir


def workflow(name):
    return (skill_dir('mdf') / 'references' / f'{name}.md').read_text()


@pytest.mark.parametrize('name,ordinary', [
    ('deliver', '已有 adhoc'), ('next', 'adhoc 按'),
    ('manual-feature', '步骤 1 调用'), ('adhoc', 'mdf.py adhoc-status'),
])
def test_pr_recovery_precedes_normal_delivery_and_adhoc_status(name, ordinary):
    text = workflow(name).split('## 工作流（唯一执行契约）', 1)[1]
    assert text.index('PR 恢复优先') < text.index(ordinary)
    assert 'pr-close-out.md' in text


def test_pr_prepare_resumes_repairs_before_finish_or_polling():
    text = workflow('pr-close-out')
    assert '### 恢复路由与返工上下文' in text
    for rule in (
        '先应用当前 until', '先于 doctor、branch、delivery status 和 adhoc-status',
        '清理前置已全部完成、detach 或删除 source 后中断', '不重新 start',
        'PR close-out 返工', '非 checklist 备注', '修复前左端点', '原验证请求',
        '父 intent', '原 PR/MR', '未完成返工先交回主链',
        '全部完成后才允许更新 PR/MR 或恢复轮询',
        '在更新 PR/MR 前的材料提交中移除',
    ):
        assert rule in text


def test_parent_closeout_survives_nested_review_and_verify():
    for name in ('code-review', 'verify'):
        assert '不得删除父 PR close-out 返工备注' in workflow(name)
    next_text = workflow('next')
    assert '子阶段结束后回到原 PR close-out' in next_text
    assert '不得将普通 next 自动升级为 deliver' in next_text
    deliver = workflow('deliver')
    assert 'PR 返工上下文优先于普通选择表' in deliver
    assert '先核当前 until' in deliver


def test_pr_retains_branch_and_owner_until_merge_and_publication_finish():
    text = workflow('pr-close-out')
    for rule in (
        'PR/MR 未完成时必须保留 source branch 和 owner worktree',
        '等待 review、返工、补验、等待合并和 closed 未 merged 都不进入清理',
        '完成固定 M 的 tag 发布与 backmerge，之后才可清理远端及本地 source',
        'CLI 始终保留 owner worktree', '恢复容错不授权任何流程提前删除',
    ):
        assert rule in text
