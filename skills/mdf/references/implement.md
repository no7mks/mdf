# Implement

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
│ 2 Implement                      │
└────────────────┬─────────────────┘
                 │
                 ├──── 实现问题可修复 ────────→ 2 Implement
                 ├──── 目标不明或无法完成 ────→ [停止并报告]
                 │
                 ▼ 实现完成且自检已记录
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
| 1 | 入口 | 约束 | 按 roster 进入 dev 或 owner 并检查 gate | worktree、设计与底座 | 2 | 停止并报告 |
| 2 | 实现 | 约束 | 按目标与设计实现并自检 | 自检命令、结果、待验项 | 3 | 未满三轮且下一步明确则 2；否则停止 |
| 3 | 记录 | 脚本 | 记录 implement gate 并提交实现 | gate、自检摘要、提交 | 结束 | 停止并报告 |

## 术语与数据结构

### 范围与前置条件

先运行 `delivery status`，读取 `roster`。
`roster.dev == 0` 时在 owner 实现，不切角色树。
`roster.dev ≥ 1` 时读取 `worktrees.dev` 列表；缺对应树则停止。
独立调用或只续办一路时用该项的 `path` 与 `branch`。deliver 对列表每一项分派
独立 subagent，不把兄弟路径传入任务。
用 `git -C <该绝对路径>` 与该路径下的绝对文件路径操作。角色树对 owner 分支执行
`git merge --no-ff`；已在该 worktree 时仍先 merge。冲突保留现场。
`roster.dev ≥ 1` 时不得在 feature 上实现（指 owner，不是 kind）。
独立调用或 deliver 步骤 4 的 subagent 将会话根切到该 dev 路径与分支（index 1
形如 `dev/feature/<slug>`），不是 owner：Cursor 对该 dev 路径调用 `move_agent_to_root`
（禁止 `move_agent_to_cloned_root`），新 shell 核对 toplevel 与当前分支；其他宿主
打开或接到已有 dev worktree，禁止新建 worktree，禁止切到 owner。未切到则停止。
deliver 步骤 3 主 Agent 续办时禁止切会话与 `move_agent_to_root`，保持 owner。
再运行 `delivery check --stage implement`。
`dev_strategy` 为 `partition` 时只做 design 派给本 index 的切片，仍不看兄弟代码。
roster.models 有值时写入本路任务；没有则不提模型或 effort。
测试完成不是前置条件。独立调用不自动分派 Agent；deliver 可按其契约分派本阶段。只修改实现；只使用 design 基线已提交的
共享代码底座，发现缺失时停止并回 design，不得本路自行创建底座。
测试争议反馈给用户，不改断言或配置绕过验证。

### 自检与交接证据

实现前按 design 的当前事实锚点读取对应事实页；已记载的当前行为以事实页为准，
不从源码重新推断契约。本次要修改已记载行为时先读对应事实页再改实现，
文档同步由 finish 的 fact update 完成；发现事实页与实现冲突时停止并报告。
在记录 gate 前逐项对照 objectives 与 design 检查实现路径、接口和错误语义；
执行当前实现适用且可运行的自检，记录命令、退出状态、结果及对应验收项。
不要求测试先完成或项目全绿；无法执行的自检逐项说明原因及留给 converge 的验证项。
自检发现本阶段可修复的实现问题时原地修复并重查。可修复指同一失败未满三轮且下一步修复动作明确；
否则视为无法完成。目标或设计不明、实现未完成时停止并报告，
不记录通过的 implement gate。摘要须区分已验证结论与未验证项，不把后续验证项写成已通过。
运行 `delivery record --stage implement --summary <实现与自检摘要>` 并提交。

