# Deliver

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 目标不明或条件缺失 ────→ [询问或报告阻塞]
                 │
                 ▼ 唯一交付目标
┌──────────────────────────────────┐
│ 2 Select                         │
└────────────────┬─────────────────┘
                 │
                 ├──── finish 已完成 ─────→ 5 Report
                 ├──── 可并行阶段 ────────→ 4 Parallel
                 ├──── 证据冲突或阻塞 ────→ [保留现场并报告]
                 │
                 ▼ 单个待办阶段
┌──────────────────────────────────┐
│ 3 Execute                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 阶段完成 ────────→ 2 Select
                 └──── 失败或待确认 ────→ [按原流程交接]
┌──────────────────────────────────┐
│ 4 Parallel                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 全部交接通过 ────→ 2 Select
                 └──── 失败或待确认 ────→ [保留各路现场并报告]
┌──────────────────────────────────┐
│ 5 Report                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 完成证据有效 ────→ [结束]
                 └──── 证据不足 ────────→ [报告实际状态]
```

## 工作流（唯一执行契约）

读取 `references/common.md`；feature 另读 `references/delivery-contract.md`。
按所选阶段完整读取其 intent 及声明的公共引用，执行原编号工作流，不以本流程摘要替代。
本 intent 是持续交付的外层协调者，不新增 CLI command、gate 或统一 workflow 状态文件。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 定位 | 约束 | 锁定一次交付及 owner worktree | 目标、分支、路径 | 2 | 询问或报告阻塞 |
| 2 | 选择 | 约束 | 核对当前证据，选择剩余步骤 | 有效产物、执行者、待办 | 完成 5；并行 4；其他 3 | 保留现场并报告 |
| 3 | 执行 | 约束 | 续办单阶段，完成后返回外层 | 原流程证据 | 2 | 按原流程交接 |
| 4 | 并行 | Subagent | 分派独立阶段，核对路径并等待交接 | 各路分支、提交、gate | 2 | 保留各路现场并报告 |
| 5 | 结果 | 约束 | 核对 finish 实际结果并报告 | 合并、清理、适用 tag 与推送 | 结束 | 报告实际状态 |

## 术语与数据结构

### 目标与持续授权

调用 `$mdf deliver` 授权从当前状态连续执行本次交付剩余工作直到 finish 完成，
包含原流程要求的本地提交、并行委托、集成与 finish 的 Gitflow 操作。
feature/bugfix 完成本地 develop 合并；release/hotfix 包含 finish 规定的 tag 与发版推送。
只完成当前一个交付，不自动启动下一个 PRP、Bug 或 release。
用户明确限制提交、推送或只读时遵守限制；与 finish 完成条件冲突时说明并询问，不能声称完成。
已有有效确认继续适用；设计确认、测试修改批准、目标变更和外部条件仍按原流程处理。
需要用户决定时暂停，收到回答后从本次暂停处续办，不要求用户重复调用每个阶段。

步骤 1 解析目标 Git 根并运行 doctor、branch，要求 ready。
优先锁定用户指定的交付；否则由当前 feature/qa/dev、bugfix、hotfix 或 release 分支确定。
feature 的 qa/dev 归属 owner feature；使用 `delivery status` 返回的 `worktrees.owner.path`。
其他分支使用 `git worktree list --porcelain` 中完整分支名对应的已有路径。
从其他目录进入时，只有上下文明确唯一交付目标才可切到它；多个候选必须询问，不按最近目录猜测。
若尚未 start，但用户已明确分支种类及 PRP/Bug/版本，则委托 `references/start.md`，
按其规则补齐必要输入并使用返回的 owner 与 roles；不自动挑选待办，不调用初始化或规划流程。
已有交付缺少 worktree 时停止，不能重新 start、抢占 checkout 或临时创建另一套分支绕过。
记录 owner 分支与仓库的绝对路径、Git common dir，以及不会被 finish 删除的主 worktree 路径。

### 从当前证据选择剩余工作

步骤 2 结合原步骤、对话确认、未完成子步骤、产物、Git 历史及执行者状态判断。
已完成且证据有效的阶段不重做；不能仅凭 gate 文件存在或一次 check 成功判断整个阶段完成，
还须核对该阶段要求的提交、语义结论和相关内容指纹。过期证据按原阶段规则补审补验。
角色尚在时从对应 qa/dev worktree 读取各路 gate 与提交，不因 owner 尚未合入就重复分派。
角色已集成并清理时读取 owner 的两路证据，不把正常清理当作缺失而重建角色。
已有执行者先接续并等待，不另起第二个 Agent 操作同一角色 worktree。

| 当前状态 | 后续处理 |
| --- | --- |
| start 未完成 | 续办 start，锁定其返回路径 |
| feature 设计或共用底座未完成 | 在 owner 委托 `references/design.md` |
| feature 两路均未完成且前置条件满足 | 并行委托 `references/write-tests.md` 与 `references/implement.md` |
| feature 仅一路未完成 | 在该角色 worktree 续办该 intent，不重跑已完成一路 |
| feature 两路完成但未收敛 | 在 owner 委托 `references/converge.md` |
| bugfix/hotfix/release 尚有已确认开发工作 | 在 owner 完成对应目标内的实现、修复与测试 |
| 实现完成且审查缺失或过期 | 在 owner 委托 `references/code-review.md` |
| 审查有效、finish 尚未完成 | 在 owner 委托 `references/finish.md`，续办其中未完成步骤 |
| finish 实际完成 | 进入 5，不因 owner 已删除而重新识别新任务 |

bugfix/hotfix/release 使用对应 Bug、热修复目标或发布范围，不套用 feature 的阶段 gate。
没有独立开发 intent 的剩余工作由主 Agent 在步骤 3 按已确认范围处理，不借 code-review 隐式扩充目标。
发现缺少设计决定或验收依据时询问；不虚构开发任务，也不把未实现的目标判定为完成。
finish 已开始而代码发生变化时按 code-review 的复核规则处理后再续办 finish，不能跳过过期检查。
步骤 3 的被委托 intent 完成后返回 2；各 intent 的“结束”只结束该次内部委托，
不结束 deliver。步骤失败时遵守原流程的恢复和停止条件，不无限重试无进展的失败。

### 并行委托与 worktree 身份

步骤 4：所有当前可并行且互不依赖的 intent 必须分别交给 subagent，不由主 Agent 串行代做。
当前明确的并行组合为 feature 的 write-tests 与 implement，须已确认并提交同一 design 与共享底座。
两路已有一条运行时，等待其结果并启动另一条可执行的空闲路；不得重复创建执行者。
只剩一路时也可交给单个 subagent，主 Agent 保持协调与核验责任。
不把有前后依赖的 converge、code-review、fact update、finish 并行；同一可写 worktree 不并发派工。
code-review 内部仍强制 3 个 subagent 同范围只读审查，按其契约执行，主 Agent 汇总修复。
资源不足时等待已有执行者释放；无法提供所需 subagent 能力时报告阻塞，不悄悄降级串行。

分派前主 Agent 从 owner 的 `delivery status` 取得现有绝对路径与分支名，
规范化后的 owner、qa、dev 路径必须两两不同，且与 Git worktree 清单中的分支绑定一致。
固定本轮 owner 的 design 基线提交；并行期间不推进 owner，不修改目标、设计或共享底座。
每个任务明确传入 MDF_ROOT、owner 路径及分支、角色绝对 worktree、预期完整分支名、
Git common dir、设计提交、对应 intent、读写边界与完成证据，不能只给相对目录或角色名称。

| subagent | 必须使用的路径与分支 | 写入职责 |
| --- | --- | --- |
| write-tests | `worktrees.qa.path`；`qa/feature/<slug>` | 原 write-tests 契约允许的测试、配置及阶段证据 |
| implement | `worktrees.dev.path`；`dev/feature/<slug>` | 原 implement 契约允许的实现及阶段证据 |
| code-review 的三名审查者 | owner 的同一绝对路径与固定 review_head | 只读，不建立角色 worktree |

主 Agent 分派前和 subagent 首次操作时都必须核对：

- 在指定路径运行 `git rev-parse --show-toplevel`，规范化绝对路径必须等于分派的 worktree。
- `git branch --show-current` 必须等于预期完整分支，不能 detached，也不能在 owner 冒充 qa/dev。
- `git rev-parse --path-format=absolute --git-common-dir` 必须等于 owner 的 Git common dir。
- 角色依原 intent 先 no-ff merge owner，随后以 `git merge-base --is-ancestor <design_commit> HEAD`
  确认包含固定共同基线，并运行对应 `delivery check --stage`。冲突或身份不符立即停止。

所有命令显式指定该 worktree 的工作目录或 `git -C`，文件写入使用该 worktree 下的绝对路径。
不得假设 subagent 继承主 Agent cwd；工具自动分配的其他 worktree 不替代 MDF 角色树。
不能绑定并验证指定路径时停止，不在默认目录开工。审查者验证 owner 与 review_head，不合并或写入。

### 等待、交接与收口

主 Agent 等待所有已派阶段完成或明确阻塞，不在任一路仍运行时执行 converge 或删除角色 worktree。
一条失败时保留另一条已完成产物；如需修改共同设计，先暂停所有仍在写入的执行者。
各路交接报告实际绝对路径、分支、最终提交 hash、gate 路径、验证/自检结果及未解决项。
主 Agent 在对应路径重新核对身份、提交和工作区状态，读取 gate，检查共同 design 指纹与职责边界；
还须将 gate 的 tests（qa）或 implementation（dev）指纹与本次对应 check 返回的当前指纹比较。
不以 subagent 的“完成”摘要替代检查。所有写入者停止且两路交接有效后才返回 2 进入 converge。
合并、测试修改批准、worktree 清理均委托 converge 原流程，不手工 cherry-pick 或删除角色来冒充集成。

单阶段结束、审查通过、版本材料写入或提交成功均不等于 deliver 完成。
步骤 5 必须取得 finish 的实际成功结果，按分支核对合并、源分支/worktree 清理、
以及 release/hotfix 的 tag 和推送；finish 删除 owner 后改用步骤 1 固定的主 worktree 核对。
若 finish 部分失败，记录已完成操作与未完成项，按其恢复规则交接，不重放已经发生的发布操作。
报告本次完成的阶段、验证、Git 结果或具体阻塞，以及所有仍存活的 subagent 和未完成交接。
上下文恢复时用上述现有产物与实际 Git 状态重新核验，不依赖未落地的内存完成标志。
