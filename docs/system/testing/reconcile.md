# Reconcile 测试

本 suite 覆盖混合流程的发布入口，不改变 gitflow 与 github-flow 的既有契约。

## 范围

| 目录 | 核对内容 |
| --- | --- |
| tests/unit/reconcile | 输入白名单、逐 commit、rename/revert、字段约束 |
| tests/e2e/reconcile | 真实 Git 的历史快照、无账本接管、证据、PR/CI 与发布顺序 |

## 验收目标

- 历史已有 Change 读取快照；缺失 Change 依固定区间补建。
- 部分归档留下未发布净增量；歧义失败时工作区不变。
- 不伪造账本，不将 fact 结论当作测试或 code-review 证据。
- 候选改变、检查缺项或失败时拒绝代发版本。
- 三类发布保持原顺序和 tag 身份；四种 workflow × mode 通道均可收尾。
- support 记录独立于 trunk 的版本和对象状态。

测试使用本地 Git 与离线平台夹具；全量回归还需保留原有双 flow suite。
运行与 JUnit 复用规则见 [测试约定](conventions.md)。
