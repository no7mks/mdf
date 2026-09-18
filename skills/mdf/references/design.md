# Design

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Clarify                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Baseline                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止并报告]
```

## 工作流（唯一执行契约）

读取 `references/delivery-contract.md`、`references/common.md`；涉及 PRP 时读取 `references/object-contract.md`。
CLI 使用 `python3 "$MDF_ROOT/scripts/mdf.py" delivery <action> --repo "$REPO_ROOT"`。
独立调用只推进当前 intent；deliver 内部委托时完成后返回调用方，由其选择下一阶段。
步骤 2 读取并内部执行 `references/clarify.md`；确认的是方案稿，底座文件由步骤 3 写入。
确认后，步骤 3 按 `assets/templates/design.md` 写入设计。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 约束 | 确认 start 记录与 objectives | PRP 或 Bug、start 记录、objectives | 2 | 停止并报告 |
| 2 | 设计 | 约束 | 委托 clarify，确认设计、测试策略及双方共用代码底座 | 用户确认的设计与底座方案 | 3 | 停止并报告 |
| 3 | 基线 | 脚本 | 写设计、policy 与底座，记录 gate 并提交共同基线 | gate、底座、设计基线提交 | 结束 | 停止并报告 |

## 术语与数据结构

### 范围与前置条件

在 design.md 中明确目标、非目标、接口、错误语义、
验收到 quick 与本交付 suite 的映射及 verification 各项适用条件。测试仅对
objectives 负责。分层后必须声明本交付 suite 名称，供 write-tests 把用例写入
对应 suite。
设计前按任务从 `docs/README.md` 定位并读取相关当前事实页，在 design.md 列出
当前事实锚点（页面路径）；没有对应事实页时写明本次将新增哪些页面，
不得把计划写进既有事实页，事实更新由 finish 的 fact update 完成。
记录 design gate 时 CLI 校验 objectives.md 与 design.md 的本地链接目标存在。
feature 的 objectives 由 start 写入；其他 kind 在 roster ≥1 时若缺则本步先写。
结束前必须把 write-tests 与 implement 后续都会依赖的共享代码底座写入仓库：
类型、接口、错误语义、明确未实现的 stub 和最小测试设施，使两路从同一提交继续，
不得各自再写一份底座。纯文档改动不制造代码；底座未就绪不得记录 design gate。

### 设计 policy 与基线

准备 policy JSON：未分层为 `{"protected_paths": ["tests/", "pyproject.toml"]}`，
不得带 `suites`；分层后必须同时给出 `suites`，例如
`{"protected_paths": ["tests/", "pyproject.toml"], "suites": ["billing"]}`。
字段不符返回 `invalid_policy`，suite 名无效或占用 quick/full 返回
`invalid_delivery_suite`，均停止并修正 policy 后重试。
`protected_paths` 列全项目实际的测试、fixture、快照、测试发现、覆盖率和告警配置
路径，包括交付 suite；manifest 验证项由 Core 保护。`suites` 为本交付 suite
名，不得使用 quick/full。
运行 `delivery record --stage design --policy-file <文件> --summary <用户确认的设计摘要>`。
提交 objectives.md、design.md、delivery.json、design gate 及共享代码底座，形成同一基线。
底座未写入该基线则不得结束。角色 worktree 已由 start 建立，本步不创建。
