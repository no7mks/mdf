# post-gitflow-start

树形：not-tree。start 成功后只承办一次 hook，不提供独立 intent。

## 工作流（唯一执行契约）

先读取 [配置接口](hooks/post-gitflow-start.md)；command 已由 Core 执行时只核结果，不重复执行。
适用 common 的日志条款；deliver 委托时继承其 until 与 confidence 策略。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check context | 约束 | 核 start 与 hook | JSON、cwd | command3；rule2；无配置返回 | start 失败不执行；缺项报告 |
| 2 | Run rule | 约束 | 在 owner 读取规则并执行一次 | cwd、规则、日志、结果 | 3 | 失败记录后 3，不重试 |
| 3 | Report | 约束 | 核结果与日志，返回 start | 执行结果与日志路径 | 返回调用方 | 失败仅汇报，不回滚 start |

## 术语与数据结构

### 执行契约

本节限定调用位置、输入和失败处理。

- start 成功创建所有 worktree、写入并提交交付材料之后调用一次。
- cwd 为新的 owner worktree；从新 worktree 解析 path，不在 qa/dev 执行。
- command 由 Core 执行；rule 由 start 的 Agent 切到 owner 后读取并执行。
- 上下文含新老 worktree 绝对路径；旧地址是发起 start 的 `--repo`。
  - command 使用 `MDF_NEW_WORKTREE` 与 `MDF_OLD_WORKTREE` 环境变量。
  - rule 的 Agent 从成功 JSON 的 `hook` 读取同名含义的
    `new_worktree`、`old_worktree` 和 `cwd`。
- 执行前输出 hook 名、path、cwd；执行后输出结果，失败时说明原因。
  - command 说明及完整 stdout/stderr 输出到 CLI stderr，并进入 CLI 运行日志。
  - rule 由 Agent 输出前后说明，并按通用运行日志契约记录执行证据。
- 失败仅汇报：start 仍成功，保留 worktree、分支和提交，不回滚，不自动重试。
- start 本身失败时不执行 hook。
