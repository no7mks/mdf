# Write Tests

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
│ 2 Cases                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 可执行测试已编写
┌──────────────────────────────────┐
│ 3 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止并报告]
```

## 工作流（唯一执行契约）

读取 `references/delivery-contract.md`、`references/common.md`；涉及 PRP 时读取 `references/object-contract.md`。
CLI 使用 `python3 "$MDF_ROOT/scripts/mdf.py" delivery <action> --repo "$REPO_ROOT"`。
独立调用只推进当前 intent；deliver 内部委托时完成后返回调用方，由其选择下一阶段。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 约束 | 强制 qa worktree 并检查前置 gate | 角色 worktree、共同设计与底座 | 2 | 停止并报告 |
| 2 | 用例 | 约束 | 按设计编写测试，确认可执行并审查覆盖 | 可执行性、覆盖 | 3 | 停止并报告 |
| 3 | 记录 | 脚本 | 记录 write-tests gate 并提交本阶段产出 | gate、覆盖摘要、提交 | 结束 | 停止并报告 |

## 术语与数据结构

### 范围与前置条件

先运行 `delivery status`，读取 `worktrees.qa.path`；缺树则停止。
用 `git -C <qa 绝对路径>` 与该路径下的绝对文件路径操作。对 owner 分支执行
`git merge --no-ff`；已在该 worktree 时仍先 merge。冲突保留现场。
不得在 feature 上编写或补写测试（指 owner `feature/<slug>`，不是 kind）。
独立调用或 deliver 步骤 4 的 subagent 将会话根切到该 qa 路径与
`qa/feature/<slug>`，不是 owner：Cursor 对该 qa 路径调用 `move_agent_to_root`
（禁止 `move_agent_to_cloned_root`），新 shell 核对 toplevel 与当前分支；其他宿主
打开或接到已有 qa worktree，禁止新建 worktree，禁止切到 owner。未切到则停止。
deliver 步骤 3 主 Agent 续办时禁止切会话与 `move_agent_to_root`，保持 owner。
再运行 `delivery check --stage write-tests`。
与 implement 互不前置，可并行。独立调用不自动分派 Agent；deliver 可按其契约分派本阶段。
只使用 design 基线已提交的共享代码底座；发现类型、接口、stub 或测试设施缺失时停止，
回 design 补底座，不得本路自行创建。错误输入与可预见的错误行为表达为输入—期望输出测试用例；
不要求针对具体实现进行错误注入，也不强制先产生红灯。

### 测试与交接证据

测试须能编译或加载执行；环境或导入故障不是有效完成证据。因尚未实现而产生的
断言失败可以接受。本阶段不要求项目全绿，也不得因断言失败拒绝记录 gate。
全绿由 converge 负责。逐项审查 objectives 覆盖与断言。
首次按确认设计编写测试与配置属于本 intent 的授权；不得改变目标或降低项目门槛。
运行 `delivery record --stage write-tests --summary <覆盖与可执行性证据>` 并提交。

