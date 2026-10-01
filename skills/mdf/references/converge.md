# 收敛（Converge）

验收中心：确认 objectives 完成，并跑 **verify on-site** 修到达成。
❌ 此处的「验」不是 verify full。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Dispatch                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 已派
┌──────────────────────────────────┐
│ 2 Join                           │
└────────────────┬─────────────────┘
                 │
                 ├──── 需测试修改批准 ────→ [主会话确认后带 --test-approval 重试 2]
                 ├──── 拒绝测试修改 ──────→ [写阻塞记录并停止]
                 ├──── 失败/缺失 ─────────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Accept                         │
└────────────────┬─────────────────┘
                 │
                 ├──── objectives 未完成或 on-site 可修 ────→ 3 Accept
                 ├──── 需测试修改批准 ──────────────────────→ [确认后 resume 回 3]
                 ├──── 拒绝测试修改 ────────────────────────→ [写阻塞记录并停止]
                 ├──── 外部阻塞或三轮无进展 ────────────────→ [记录阻塞并停止]
                 │
                 ▼ objectives 完成且 on-site 通过
┌──────────────────────────────────┐
│ 4 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止并报告]
```

## 工作流（唯一执行契约）

读取 `references/delivery-contract.md`、`references/common.md`。
CLI：`python3 "$MDF_ROOT/scripts/mdf.py" delivery <action> --repo "$REPO_ROOT"`。
独立调用只推进当前 intent；deliver 内部委托时完成后返回调用方。
启动恰好 1 个 owner subagent 执行步骤 2–4；当前 Agent 不得代做。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Dispatch | Subagent | 启动恰好 1 个 owner subagent 执行步骤 2–4 | 已派执行者 | 2 | 停止并报告 |
| 2 | Join | 约束 | 按需集成角色或检查 owner | 集成/状态 | 3 | 待批准重试；拒绝停；其他停 |
| 3 | Accept | 约束 | objectives + on-site；循环到达成 | checklist、on-site | 4 | 可修回 3；拒绝或阻塞停 |
| 4 | Record | 脚本 | 记录 converge gate 并提交 | gate、提交 | 结束 | 停止并报告 |

## 术语与数据结构

### 执行者

- 独立调用与 deliver 委托均启动恰好 1 个 owner subagent 执行步骤 2–4。
- 当前 Agent 不得代做 Join、Verify 或 Record。不计入 roster，不可配人数。
- 无法提供 subagent 时停止，不降级代做。
- 已有 converge 执行者先等待，不对同一
  owner 另开第二个。
- subagent 绝对路径绑定 owner；禁止新建 worktree、禁止要求用户切换；
  禁止 `move_agent_to_root`。
- 绑定成功后横幅用 owner 的路径与分支。
- 结束后再运行 `delivery check --stage converge`；确认 gate 已跟踪。
- 需测试修改批准时 subagent 停止并交出未决；主会话确认后 resume
同一 subagent。
- `--auto-pilot` / `--yolo` 由 subagent 自裁定并记录批准，不回主会话提问。
- 主会话确认后 resume 回 3。

### 范围与前置条件

仅在 owner 工作。`needs_design: yes` 时：

- 按 roster 的 qa/dev strategy 集成（`best-of-n` / `partition`），规则同前。
- 运行 `delivery integrate`；合并后清理角色 worktree。
- 随后 `delivery check --stage converge`。

续办与清理：

- 续办仍调用同一命令；脚本核对已记录提交是 owner 的祖先，现存角色未改变，随后只清理剩余角色。
- 角色均已清理时同样核验记录，不重建角色、不再次合并。
- ❌ 缺少有效记录却缺角色时停止并报告。
- `stale_integration` 表示现场被其他操作改变，停止。

`needs_design: no`：无角色可合；确认 owner 干净且开发改动已提交。

### Accept（objectives + on-site）

1. 核对 `objectives.md` 大步骤 checklist：本次范围内项须为 `[x]`；未完成则继续开发/勾选，
   不得虚构完成。
2. 运行 `$mdf verify run --level on-site`（涉及 module 的 lint+build+quick +
   本分支相对 start_commit 新增/改动的测试；可加 Agent/Jev 选题）。
3. ❌ 不得用 verify full 或 `delivery verify`（smoke/release）冒充本步。
4. 失败时遵守「测试失败工作流」（单用例复测 → 修一个复测一个 → 再继续）。
5. 可修实现则修；改测试/门槛须批准（防改测试掩盖真 bug）。
6. 循环直至 objectives 完成且 on-site 绿，或阻塞停止。

阻塞写入 `gates/converge-blocked.md`（目标决定、拒绝测试修改、三轮无进展）。

### Record

运行 `delivery record --stage converge --summary <objectives 与 on-site 摘要>`；
如需测试批准一并传入。提交 gate 与相关产物。
