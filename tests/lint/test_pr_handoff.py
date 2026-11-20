"""deliver/next 与 PR 的恢复优先级和返工交接契约。"""
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
    assert 'pr.md' in text


def test_pr_prepare_resumes_repairs_before_finish_or_polling():
    text = workflow('pr')
    assert '### 恢复路由与返工上下文' in text
    for rule in (
        '先应用当前 until', '先于 doctor、branch、delivery status 和 adhoc-status',
        '清理前置已全部完成、detach 或删除 source 后中断', '不重新 start',
        'PR 返工', '非 checklist 备注', '修复前左端点', '原验证请求',
        '父 intent', '原 PR/MR', 'open 且有未完成返工时先恢复',
        '全部完成后才允许更新 PR/MR 或恢复轮询',
        '在更新 PR/MR 前的材料提交中移除',
    ):
        assert rule in text


def test_pr_prepare_reuses_committed_candidate():
    text = workflow('pr').split('### 候选材料准备', 1)[1].split('### 完成与交接', 1)[0]
    assert '统一由 [consolidate]' in text
    assert 'PR Prepare 核对其结果' in text
    assert 'incremental-integration 中执行 incr-consolidate' in text


def test_parent_closeout_survives_nested_review_and_verify():
    for name in ('code-review', 'verify'):
        assert '不得删除父 PR 返工备注' in workflow(name)
    next_text = workflow('next')
    assert '子阶段结束后回到原 pr' in next_text
    assert '不得将普通 next 自动升级为 deliver' in next_text
    deliver = workflow('deliver')
    assert 'PR 返工上下文优先于普通选择表' in deliver
    assert '先核当前 until' in deliver


def test_pr_retains_branch_and_owner_until_merge_and_publication_finish():
    text = workflow('pr')
    for rule in (
        'PR/MR 未完成时必须保留 source branch 和 owner worktree',
        '等待 review、返工、补验、等待合并和 closed 未 merged 都不进入清理',
        '须先完成 publish，close-out 再核对固定发布点与适用的 backmerge',
        'CLI 始终保留 owner worktree', '恢复容错不授权任何流程提前删除',
    ):
        assert rule in text


def test_only_pr_entry_binds_goal_and_closeout_only_resumes_after_merge():
    text = workflow('pr')
    assert '### Goal 与持续推进' in text
    assert '再进行远端集成、材料准备或恢复' in text
    for name in ('close-out', 'adhoc-close-out'):
        text = workflow(name)
        assert 'pr-close-out.md' in text
        assert '不在 close-out 内创建 PR、轮询 CI 或准备候选材料' in text
        assert '#goal-与持续推进' not in text


@pytest.mark.parametrize('state,action', [
    ('没有未完成 Goal', '创建本次 pr Goal'),
    ('阶段 Goal 的完成判据已全部满足', '先核验证据并置 complete'),
    ('未完成 Goal 已覆盖本次 pr', '复用，不重建'),
    ('未完成 Goal 范围更大', '加入其剩余工作，保留原目标与其他未完成项'),
    ('无关且未完成 Goal', '不自动 cancel、覆盖或假称完成'),
])
def test_pr_goal_selection_preserves_existing_work(state, action):
    text = workflow('pr').split('### Goal 与持续推进', 1)[1].split('### 提交前远端集成', 1)[0]
    row = next(line for line in text.splitlines() if line.startswith(f'| {state} |'))
    assert action in row


def test_pr_goal_survives_repairs_merge_and_parent_handoff():
    text = workflow('pr').split('### Goal 与持续推进', 1)[1].split('### 提交前远端集成', 1)[0]
    for rule in (
        '轮询、主链外返工与重新提交始终沿用同一个 Goal',
        'CI 全绿或 review 通过不能完成 Goal',
        '`status=merged`、`completed=true`',
        '父 Goal 仍有剩余工作时不得置 complete',
        '不得声称已修改宿主 objective',
        '不越过 deliver 的 until、只读限制或用户暂停',
    ):
        assert rule in text
    assert 'pr.md#goal-与持续推进' in workflow('deliver')


def test_pr_tracks_origin_and_merge_runs_and_rechecks_before_completion():
    text = workflow('pr')
    polling = text.split('### 当前调用内轮询', 1)[1].split('### 反馈修复与重新提交', 1)[0]
    for rule in (
        '发起 PR/MR 和执行 merge',
        'run ID、attempt、URL',
        '--origin-run <id>',
        '全部 job 与 step',
        '非 required checks',
        'PR 已 merged 但关联运行未结束时，保持 Goal active',
        '目标远端第一父链，随即复查平台状态',
        '检查证据一致时立即返回 `merged`',
        'cancelled、timed_out、action_required',
        '合并后的失败不得向已合入的 source 追加提交',
        '平台各查询均完整返回且已确认的关联范围为空时',
    ):
        assert rule in polling
    goal = text.split('### Goal 与持续推进', 1)[1].split('### 提交前远端集成', 1)[0]
    assert 'CLI 合并核验与关联 CI 收尾均通过' in goal
    assert '必要但不充分' in goal


@pytest.mark.parametrize('name', ['pr', 'next', 'deliver', 'pr-close-out'])
def test_merged_recovery_cannot_bypass_ci_completion(name):
    assert 'merged 但关联 CI 未收尾或缺少证据时先恢复 pr' in workflow(name)


def test_pr_mode_default_completion_and_mandatory_unticked_continuation():
    policy = workflow('deliver-policy')
    assert '默认 local 与 PR mode 均无截止点，直到交付的最后一个阶段完成' in policy
    assert '显式 `--until close-out` 允许 pr 等到 merged 后停止' in policy
    contract = workflow('delivery-contract')
    assert '交付清单记录 catch-up、consolidate' in contract
    for name in ('deliver', 'next'):
        assert '前置全勾后按 `delivery route` 选择下一阶段' in workflow(name)
    for name in ('manual-feature', 'adhoc'):
        assert '前置全勾后按 [PR 恢复路由]' in workflow(name)
    assert '实际 merged、合并核验与关联 CI 收尾均通过后，pr 完成' in workflow('pr')


def test_pr_repairs_return_to_pr_and_submission_preserves_deliver_boundaries():
    bug = workflow('bug-close')
    assert 'consolidate | 当前材料收敛步骤' in bug
    pr = workflow('pr')
    assert '低 confidence 返回 deliver 步骤 6' in pr
    assert '被截止的 pr 不绑定新 Goal、不准备材料、不 push 或轮询' in pr
    assert '在当前 pr 调用内持续处理' in pr
    finish = workflow('pr-close-out')
    assert '│ 1 Check merged' in finish and '树形：not-tree。' not in finish
