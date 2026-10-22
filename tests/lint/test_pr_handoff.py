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


@pytest.mark.parametrize('name', ['close-out', 'adhoc-close-out'])
def test_pr_entry_binds_goal_before_preparation_or_recovery(name):
    text = workflow(name).split('## 工作流（唯一执行契约）', 1)[1]
    assert 'pr-close-out.md#goal-与持续推进' in text
    assert '绑定 Goal，再执行首次准备或恢复' in text


@pytest.mark.parametrize('state,action', [
    ('没有未完成 Goal', '创建本次 PR close-out Goal'),
    ('阶段 Goal 的完成判据已全部满足', '先核验证据并置 complete'),
    ('未完成 Goal 已覆盖本次收口', '复用，不重建'),
    ('未完成 Goal 范围更大', '加入其剩余工作，保留原目标与其他未完成项'),
    ('无关且未完成 Goal', '不自动 cancel、覆盖或假称完成'),
])
def test_pr_goal_selection_preserves_existing_work(state, action):
    text = workflow('pr-close-out').split('### Goal 与持续推进', 1)[1].split('### 提交前远端集成', 1)[0]
    row = next(line for line in text.splitlines() if line.startswith(f'| {state} |'))
    assert action in row


def test_pr_goal_survives_repairs_merge_and_parent_handoff():
    text = workflow('pr-close-out').split('### Goal 与持续推进', 1)[1].split('### 提交前远端集成', 1)[0]
    for rule in (
        '轮询、主链外返工、重新提交与合并后收尾始终沿用同一个 Goal',
        'CI 全绿、review 通过、PR 已 merged 或 tag 已发布，均不能单独完成 Goal',
        '仅 `completed=true` 且实际结果核验通过',
        '父 Goal 仍有剩余工作时不得置 complete',
        '不得声称已修改宿主 objective',
        '不越过 deliver 的 until、只读限制或用户暂停',
    ):
        assert rule in text
    assert 'pr-close-out.md#goal-与持续推进' in workflow('deliver')
