# MDF 协议概览

MDF 以唯一 `$mdf <command>` Skill 发布。公共契约、模板与确定性 CLI 都是该
Skill 的内部材料，不可单独调用。

## 命令

| 命令 | 行为 |
| --- | --- |
| `init-repo` | 初始化或更新配置，必要时逐题收敛基线与验证命令 |
| `review-doc` | 澄清并维护单个 Requirement 或 Bug |
| `finish` | 在 Gitflow 分支上审计并完成收口 |
| `audit` | 只读执行 change audit 或 release audit |
| `archive` | 移动 closed 对象并重写仓库内引用 |
| `grill <议题>` | 对计划或决策逐题压力测试 |

每次外层工作流都从 clean worktree 开始，绝不自动 commit。`init-repo` 与
`review-doc` 需要澄清时调用内部 grill 工作流；`finish` 在写入前运行内部 audit。

## 不变量

- manifest 为 `initializing` 时，只能用 `$mdf init-repo` 续办；转为 `ready`
  前必须具备八项基线和非空验证命令。
- 当前事实必须有可验证证据；Requirement、Bug 与 Change 不得替代当前事实。
- release closeout 仅接受零 finding 的审计摘要，且不接受 waiver。
- 所有版本号、对象状态、Bug outcome 和归档规则以 Skill 内的当前契约为准。
