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
        '完成固定 M 的 tag 发布与 backmerge，之后才可清理远端及本地 source',
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


def test_pr_tracks_originating_run_and_all_jobs_after_merge():
    text = workflow('pr')
    polling = text.split('### 当前调用内轮询', 1)[1].split('### 反馈修复与重新提交', 1)[0]
    for rule in (
        '发起该 PR/MR 的 workflow run / pipeline',
        'run ID、attempt、URL',
        '不能仅按 PR head SHA 查找',
        '全部 job 与 step',
        '非 required checks',
        'PR 已 merged 但关联运行未结束时，保持 Goal active',
        'cancelled、timed_out、action_required',
        '合并后的失败不得向已合入的 source 追加提交',
        '查询失败、权限不足或关联不明不能当作没有 CI',
    ):
        assert rule in polling
    goal = text.split('### Goal 与持续推进', 1)[1].split('### 提交前远端集成', 1)[0]
    assert 'CLI 合并核验与关联 CI 收尾均通过' in goal
    assert '必要但不充分' in goal


@pytest.mark.parametrize('name', ['pr', 'next', 'deliver', 'pr-close-out'])
def test_merged_recovery_cannot_bypass_ci_completion(name):
    assert 'merged 但关联 CI 未收尾或缺少证据时先恢复 pr' in workflow(name)


def test_pr_mode_default_cutoff_and_mandatory_unticked_continuation():
    policy = workflow('deliver-policy')
    assert 'PR mode 为 `--until pr`' in policy
    assert '显式 `--until close-out` 允许 pr 等到 merged 后停止' in policy
    contract = workflow('delivery-contract')
    assert '- close-out（pr merged 后必须续办；不设 checkbox）' in contract
    for name in ('deliver', 'next', 'manual-feature', 'adhoc'):
        assert 'merged 后必选无 checkbox 的 close-out' in workflow(name)
    assert 'close-out 只核实际结果，不预勾、不补勾' in workflow('pr')


def test_pr_repairs_return_to_pr_and_submission_preserves_deliver_boundaries():
    bug = workflow('bug-close')
    assert 'PR mode 的 pr | pr 步骤 2' in bug
    pr = workflow('pr')
    assert '低 confidence 返回 deliver 步骤 6' in pr
    assert '被截止的 pr 不绑定新 Goal、不准备材料、不 push 或轮询' in pr
    assert '不得回到合并后 close-out' in pr
    finish = workflow('pr-close-out')
    assert '│ 1 Check merged' in finish and '树形：not-tree。' not in finish
