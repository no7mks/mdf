# Implement

## 决策树

```text
┌────────────────────────┐
│ 1 Check                │
└────────────────────────┘
             ▼
┌────────────────────────┐
│ 2 Implement            │
└────────────────────────┘
             ▼
┌────────────────────────┐
│ 3 Record               │
└────────────────────────┘
```

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 约束 | 检查 implement 前置 gate | 已提交共同设计 | 2 | 停止并报告 |
| 2 | 实现 | 约束 | 依据 objectives 与 design 完成实现 | 实现产出 | 3 | 停止并报告 |
| 3 | 记录 | 约束 | 记录 implement gate 并提交实现 | 实现交接 | 结束 | 停止并报告 |

## 执行约束

读取 `references/delivery-contract.md`、`references/common.md` 与相关对象契约。
CLI 使用 `python3 "$MDF_ROOT/scripts/mdf.py" delivery <action> --repo "$REPO_ROOT"`。
一次调用只推进当前 intent；不得自动触发下一用户入口。

运行 `delivery check --stage implement`。测试完成不是前置条件。
在 feature 或 dev/<slug> 工作，只修改实现；测试争议反馈给用户，不改断言或配置绕过验证。
运行 `delivery record --stage implement --summary <实现与自检摘要>` 并提交。

