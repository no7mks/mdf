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
一次调用只推进当前 intent；不得自动触发下一用户入口。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 约束 | 确认 feature 的 start 记录与 objectives | PRP、start 记录、objectives | 2 | 停止并报告 |
| 2 | 设计 | 约束 | 委托 clarify，确认设计、测试策略及底座范围 | 用户确认、设计内容 | 3 | 停止并报告 |
| 3 | 基线 | 脚本 | 写设计与 policy，记录 gate 并提交共同基线 | gate、设计基线提交 | 结束 | 停止并报告 |

## 术语与数据结构

### 范围与前置条件

步骤 2 读取并内部执行 `references/clarify.md`；确认后，步骤 3 按 `assets/templates/design.md` 写入设计。
在 design.md 中明确目标、非目标、接口、错误语义、
验收到测试类别的映射及 verification 各项适用条件。测试仅对 objectives 负责。
按需创建类型、接口、明确未实现的 stub 和最小测试设施；不为纯文档改动制造代码。

### 设计 policy 与基线

准备 policy JSON：`{"protected_paths": ["tests/", "pyproject.toml"]}`，列全项目实际的
测试、fixture、快照、测试发现、覆盖率和告警配置路径；manifest 验证项由 Core 保护。
运行 `delivery record --stage design --policy-file <文件> --summary <用户确认的设计摘要>`。
提交 objectives.md、design.md、delivery.json、design gate 及共享底座，形成同一基线。
用户选择并行时在提交后运行 `delivery parallel`，交接 qa/dev worktree；不自动分派 Agent。
