# Deliver

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 尚未 start 且委托成功 ─────→ 1 Resolve
                 ├──── start 失败 ────────────────→ [按 start 交接]
                 ├──── 须询问 ────────────────────→ [询问]
                 ├──── 不可恢复错误或死硬阻塞 ────→ [停止并报告]
                 │
                 ▼ 唯一交付目标
┌──────────────────────────────────┐
│ 2 Select                         │
└────────────────┬─────────────────┘
                 │
                 ├──── close-out 已完成 ────→ 5 Report
                 ├──── 可并行阶段 ──────────→ 4 Parallel
                 ├──── 证据冲突或阻塞 ──────→ [保留现场并报告]
                 │
                 ▼ 单个待办阶段
┌──────────────────────────────────┐
│ 3 Execute                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 阶段完成 ──────────────────────────────→ 2 Select
                 ├──── auto-pilot 非 yolo 的 Gitflow 关口 ────→ 6 Confirm closeout
                 └──── 失败或非该关口的待确认 ────────────────→ [按原流程交接]

仅步骤 2「可并行阶段」进入，不是步骤 3 的后续。

┌──────────────────────────────────┐
│ 4 Parallel                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 全部交接通过 ────→ 2 Select
                 └──── 失败或待确认 ────→ [保留各路现场并报告]

仅步骤 2「close-out 已完成」进入，不是步骤 4 的后续。

┌──────────────────────────────────┐
│ 5 Report                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 完成证据有效 ────→ [结束]
                 └──── 证据不足 ────────→ [报告实际状态]

仅步骤 3「auto-pilot 非 yolo 的 Gitflow 关口」进入，不是步骤 5 的后续。

┌──────────────────────────────────┐
│ 6 Confirm closeout               │
└────────────────┬─────────────────┘
                 │
                 ├──── 未决 ────────────────────────→ 6 Confirm closeout
                 ├──── 拒绝 ────────────────────────→ [保留现场并停止]
                 ├──── 确认 ────────────────────────→ [委托 close-out 步骤 10，完成后回 2]
                 └──── finish 10 停止或部分失败 ────→ [按其恢复规则交接并报告]
```

## 工作流（唯一执行契约）

读取 `references/common.md` 与 `references/delivery-contract.md`。
步骤 4、5 由步骤 2 进入，不是步骤 3 的后续。步骤 6 由步骤 3 的 Gitflow 关口进入。框序受编号约束仍按 1–6 绘制。
按所选阶段完整读取其 intent 及声明的公共引用，执行原编号工作流，不以本流程摘要替代。
审查阶段读取 `references/code-review.md`；fact 阶段读取 fact-audit，须修复时另读 fact-update。

本 intent 是持续交付的外层协调者，不新增 deliver CLI、交付阶段 gate 或统一 workflow 状态文件。
不按 branch kind 另写交付流程；靠 `needs_design`、roster 与 objectives
checklist 勾选选型（release 另读 `has_dev`；不靠 `0,0` 发明开发阶段）。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve | 约束 | 锁定交付与 owner | 目标、分支、路径 | 锁定→2；start 委托成功→1 | start 失败交接；须问；死硬停 |
| 2 | Select | 约束 | 按选择表选剩余步骤 | 产物、执行者、待办 | 完成 5；并行 4；其他 3 | 冲突或阻塞则保留现场并报告 |
| 3 | Execute | 约束 | 按原 intent 续办单阶段 | 原流程证据 | 完成→2；AP 非 yolo 关口→6 | 失败/非关口待确认→原流程交接 |
| 4 | Parallel | Subagent | 分派独立阶段，核对路径并等待交接 | 各路提交与勾选意向 | 2 | 保留各路现场并报告 |
| 5 | Report | 约束 | 核对 finish 实际结果，完成 Goal 并报告 | 合并、清理、适用 tag 与推送 | 结束 | 报告实际状态 |
| 6 | Confirm closeout | 约束 | 确认收口 | 答复 | 续办 close-out 10 后回 2 | 拒绝停；未决留 6；finish 失败按其恢复交接 |

## 术语与数据结构

### 目标与持续授权

调用 `$mdf deliver [<target>] [--auto-pilot] [--yolo]` 授权从当前状态连续执行本次交付
剩余工作直到 close-out 完成。

- 授权含尚未完成的 start，以及原流程要求的本地提交、并行委托、集成与 finish 的 Gitflow 操作。
- target 是唯一位置参数，不是 `--` option；`--auto-pilot` 与 `--yolo` 可在其前或后。
- target 与这些 option 都省略时仍是 deliver。

完成范围：

- feature/bugfix 完成本地 develop 合并；release/hotfix 包含 finish 规定的 tag 与发版推送。
- 只完成当前一个交付，不自动启动下一个 PRP、Bug 或 release。
- 用户明确限制提交、推送或只读时遵守限制。
  - 与 finish 完成条件冲突时说明并询问，不能声称完成。

确认与暂停：

- 已有有效确认继续适用。
- 默认模式：设计确认、测试修改批准、目标变更和外部条件仍按原流程处理。
  - 需要用户决定时暂停，收到回答后从本次暂停处续办，不要求用户重复调用每个阶段。
- `--auto-pilot` 与 `--yolo` 按下方策略把这些决定改为主 Agent 自裁定。

步骤 1 解析目标 Git 根并运行 doctor、branch，要求 ready。按下列顺序锁定交付：

1. 先由当前 feature/qa/dev、bugfix、hotfix 或 release 分支推导在途交付；结果即下文「当前已锁定」的交付。
   - 任一 kind 的 qa/dev 角色分支归属其 owner；使用 `delivery status` 返回的 `worktrees.owner.path`。
   - 其他分支使用 `git worktree list --porcelain` 中完整分支名对应的已有路径。
2. 再解析本次调用的 target（见下）；有唯一对象时按下文 target 规则锁定或停止。
3. 无 target 时优先锁定用户在对话中指定的交付，否则沿用当前已锁定的交付。

- 从其他目录进入时，只有上下文明确唯一交付目标才可切到它。
  - 多个候选必须询问，不按最近目录猜测。
  - `--auto-pilot` 下多个在途交付仍无法唯一锁定时属死硬阻塞。

尚未存在本次交付时委托 `references/start.md`：

- 已由 target 或用户指定 kind 与 PRP/Bug/版本则直接使用；未指定则按其步骤 1 列出候选。
- 默认模式询问用户选择；`--auto-pilot` 由主 Agent 按仓库证据与对话上下文选定唯一目标。
- 不调用初始化或规划流程，不发明 release/hotfix 版本。
- start 成功后回到 1；start 失败或停止则按其交接结束，不回 1。

已有交付与 start 返回后：

- ❌ 已有交付缺少 worktree 时停止，不能重新 start、抢占 checkout 或临时创建另一套分支绕过。
- start 返回后使用其 owner 与 roles，再创建 Goal。
- 记录 owner 分支与仓库的绝对路径、Git common dir，以及不会被 finish 删除的主 worktree 路径。

### target

位置参数至多一个；第二个及以后的非 option token 停止并询问。

已知 option 为 `--auto-pilot`、`--yolo` 与下表各项。
除这些外，以 `--` 开头的 token 不是 target，视为未知调用参数并停止。

| option | 取值 |
| --- | --- |
| `--roster` | `solo` / `min-tdd` / `competing-pair` / `coop-pair` |
| `--qa-strategy` / `--dev-strategy` / `--review-strategy` | 后跟一个取值 |
| `--write-tests-model` / `--implement-model` / `--code-review-model` | 每个 `--*-model` 后跟一个 token |

- 尚未 start 时把 `--roster` 转交给 start；已有交付再带 `--roster` 则停止。
- 委托 start、design、code-review 时原样转交细项。
- 省略 target 时不在此步选型，继续上方既有锁定规则。

按下列顺序自动分辨 Proposal 与 Bug，命中唯一对象即停止：

1. 完整 ID：符合 `prp-<序号>` 则为 Proposal；符合 `bug-<4 位字符>` 则为 Bug。
2. 否则运行 `list --repo "$REPO_ROOT"`（proposal 与 bug，不限 status），在返回的 `id` 中精确匹配。
   - 仍无则用去掉 `prp-`/`bug-` 前缀的本体、以及 `path` 文件名中的 slug 各匹配一次。
   - 不匹配 title，不把 jot ID、SemVer 或路径当成功值。
3. 按唯一命中的对象处理：
   - 唯一命中 Proposal → feature，将该 PRP ID 交给 start。Proposal 对象
     已有在途交付则报告错误并停止，不续办、不重新 start；以 `list` 的 `in_progress` 为准。
   - 唯一命中 Bug：本地已存在 `bugfix/<Bug ID>` 或其 worktree 时，该 bugfix 为在途交付；
     若当前已锁定另一交付则报告错误并停止，不续办、不重新 start。
   - 唯一命中 Bug，当前已锁定 release 或 hotfix、Bug 为 active `open` 且无上述 bugfix 分支；
     此时不 start、不改绑，将该 Bug 记入本次剩余开发工作。
   - 唯一命中 Bug 的其他情况 → bugfix，将该 Bug ID 交给 start。

- 零命中、跨类型或多对象命中时询问，不猜测。
- `--auto-pilot` 对 target 分不清就询问，不自裁定。
- 完整 ID 形态合法但 `list` 无此对象时报告缺失并停止。
- target 与当前已锁定的另一交付冲突时报告错误并停止，不改绑。

### auto-pilot

启用条件：

- 仅 `$mdf deliver --auto-pilot` 或 `$mdf deliver --yolo` 启用；默认 `$mdf deliver` 不启用。
- `--yolo` 隐含本策略；下文写 `--auto-pilot` 处对 `--yolo` 同样适用，除非写明例外。

委托子 intent 时把本策略作为外层约束：

- 原文中的询问、确认、批准与选择改由主 Agent 依据仓库证据、已确认目标和本次范围自行裁定。
  - 在摘要或 objectives 交接说明中写明依据，不向用户提问、不等待确认。
- 内部 clarify 不轮询用户；主 Agent 形成共同理解并写入确认文本。
- converge 的 `--test-approval` 记录该裁定与理由。
- ❌ 不得削弱验收或把未实现目标判为完成。

死硬阻塞才停止：

- CLI/Git/工具不可恢复失败。
- 无可启动目标（无合格 ready PRP、无合格 open Bug，且未指定合法 release/hotfix 版本）。
- 已有交付缺少 worktree。
- 用户明确只读或禁止提交/推送且与完成条件冲突。
- 必须切换 worktree 但宿主无法由 Agent 完成。
- 凭据、origin 一致性等仓库外条件缺失。
- 同一失败连续三轮无进展。
- 不改写用户明确禁止的范围就无法继续。

target 分不清就询问，不列入自裁定。除此之外不因“想听用户意见”而暂停。

| 情形 | 处理 |
| --- | --- |
| 默认模式出现多个候选，或任何模式下 target 分不清 | 须询问 |
| auto-pilot 能凭仓库证据与对话上下文定出唯一目标 | 不询问，裁定后走通过 |
| 多个在途交付无法唯一锁定，以及其他死硬条件 | 走死硬阻塞 |

唯一预定确认：close-out 步骤 9 通过、即将调用 `finish-gitflow` 之前。

- 展示将合入的目标主线、源分支、将删除的 worktree 与源分支，以及 release/hotfix 的 tag 与推送。
- 该确认只在步骤 6 进行；未决留在步骤 6。
- 取得明确确认后才委托 close-out 从步骤 10 续办；拒绝则保留现场并停止，不合并、不删 worktree。
- 此关口不是死硬阻塞，是 auto-pilot 相对完全无人值守的唯一用户确认。
- `--yolo` 跳过此关口：步骤 9 通过后直接执行步骤 10，不展示、不等待确认。
- 独立 `$mdf finish` 与默认 `$mdf deliver` 不增加该关口。

### Goal

Goal 指宿主提供的目标/待办设施（如 Cursor 的 CreateGoal/UpdateGoal）。
宿主没有该设施时跳过本节全部 Goal 操作，改在步骤 5 的最终报告中说明进度与完成判据。

步骤 1 锁定一次交付及 owner worktree，创建 Goal；
objective 写明交付标识与完成判据（close-out 实际完成）。
每次 deliver 会话只创建一次；阻塞或暂停时保持 active，不代用户暂停，续办时不重建。
已有同一交付的 Goal 时复用；内部委托传入该 Goal，子 intent 不得提前将它置 complete。
Goal 只表达交付进行中或已完成，不替代各阶段证据与报告。
步骤 5 核对 finish 实际成功后才置 complete；证据不足或部分失败时保持 active 并报告实际状态。

### 从当前证据选择剩余工作

步骤 2 结合 `objectives.md` 勾选、`delivery.json` 身份、对话确认、未完成子步骤、
产物、Git 历史及执行者状态判断。按下表自上而下命中即停止，不并行套用多行。

- **进度只认 objectives 勾选**；不以 `gates/*.json` 或一次 `delivery check` 选型。
  - report（code-review.md / verify.branch.json / fact-audit.md）只证明做过与声称结果。
- 角色尚在时从对应 qa/dev worktree 读取各路提交与交接说明，不因 owner 尚未合入就重复分派。
- 角色已集成并清理时读取 owner 的两路证据，不把正常清理当作缺失而重建角色。
- 已有执行者先接续并等待，不另起第二个 Agent 操作同一角色 worktree。

可选加速（见 `common.md`「Jev 可选加速」）：

- 对照下表前，仅当状态语义仍歧义且 tool 可用时。
- 调用：`choice`；state = 交付摘要与 objectives 勾选。
- 选项键取下表「当前状态」短标签，或 `ask`。
- objectives 勾选已明确时 ❌ 不调。
- 采信后落入表中同一「后续处理」；`ask` 或未采信走主 Agent。
- 不扩大授权、不跳过用户确认。

| 当前状态 | 后续处理 |
| --- | --- |
| start 未完成 | 续办 start，锁定其返回路径 |
| release 缺 integrate checklist 项或正文未写工作线 | 停止；须有 integrate 项且工作线三选一 |
| release integrate 未勾 | 执行 `$mdf integrate`（同 worktree 不开通道；跨 worktree 开通道）；不联调不得留未勾 |
| `needs_design: yes` 且 design 未勾 | 在 owner 委托 `references/design.md` |
| roster ≥1、未完成路数 ≥2 且前置满足 | 并行委托 write-tests / implement |
| roster ≥1 且全部 qa/dev 中恰好一路未完成 | 主 Agent 用 git -C 续办，不切会话 |
| `needs_design: yes` 且 roster `0,0`，write-tests/implement 未勾 | owner 串行 write-tests → implement |
| objectives 的 owner 开发项未勾 | owner 按 objectives 完成开发（`has_dev: no` 时该项须已由 start 预勾） |
| owner 开发（或等价开发项）已勾且 converge 未勾 | 在 owner 委托 `references/converge.md` |
| release 跨 worktree 联调且对端验收未通过 | 保持通道，send 本端结果并等对端；不进入审查 |
| release 联调且尚未确认无更多代码修改 | 通道内双方确认冻结；不进入审查 |
| converge 已勾（或无未勾 converge 项）、code-review 未勾 | owner 委托 `code-review.md`（release 另须 integrate 已勾） |
| code-review 已勾、verify branch 未勾 | 委托 `references/verify.md`（branch；失败现场修到绿） |
| verify branch 已勾、fact audit 未勾 | 委托 fact-audit；必要时 fact-update 后重审 |
| fact 已勾、close-out 未勾 | 在 owner 委托 `references/close-out.md` |
| close-out 实际完成 | 进入 5，不因 owner 已删除而重新识别新任务 |

剩余工作与失败处理：

- release/hotfix 可修 Bug：不另开 bugfix，不写 bugfix child Change。
- 步骤 3 的被委托 intent 完成后返回 2；各 intent 的“结束”只结束该次内部委托，不结束 deliver。
- 步骤失败时遵守原流程的恢复和停止条件，不无限重试无进展的失败。

### 并行委托与 worktree 身份

并行阶段读取 `references/write-tests.md` 与 `references/implement.md`。

步骤 4：所有当前可并行且互不依赖的 intent 必须分别交给 subagent，不由主 Agent 串行代做。

- roster ≥1 时并行组合为全部 qa 的 write-tests 与全部 dev 的 implement。
  - 须已确认并提交同一 design 与共享底座。
- qa 与 dev 互不传入路径；同侧多路亦互不传入兄弟路径。
- 两路已有一条运行时，等待其结果并启动另一条可执行的空闲路；不得重复创建执行者。
- 仅一路未完成走步骤 3，由主 Agent 用该角色绝对路径与 `git -C` 续办，不走步骤 4。
  - 禁止把主 Agent 会话切离 owner，禁止 `move_agent_to_root`。
- 步骤 4 的 subagent 按其 intent 用角色绝对路径操作，不切会话根；禁止新建
  worktree、禁止切到 owner、禁止要求用户切换；禁止 `move_agent_to_root`。
  - roster `0,0` 不走步骤 4。
- 不把有前后依赖的 converge、code-review、fact update、finish 并行；同一可写 worktree 不并发派工。
- design 与 converge 不走步骤 4；由各 intent 自行启动恰好 1 个 owner subagent。
  - 主 Agent 委托原 intent 后等待其完成，期间不写入 owner。
- code-review 内部按 roster.reviewers 启动独立 subagent 只读审查，按其契约执行，主 Agent 汇总修复。
- 分派时只把该 intent 在 roster.models 中的值写入对应任务，按口语描述现场解析（可多个模型）。
  - 没有该键则该路不提模型或 effort。
  - 不得把其他 intent 的模型写入本路任务。
- 资源不足时等待已有执行者释放；无法提供所需 subagent 能力时报告阻塞，不悄悄降级串行。

分派前主 Agent 从 owner 的 `delivery status` 取得现有绝对路径与分支名：

- 规范化后的 owner、qa、dev 路径必须两两不同，且与 Git worktree 清单中的分支绑定一致。
- 固定本轮 owner 的 design 基线提交；并行期间不推进 owner，不修改目标、设计或共享底座。
- 每个任务明确传入下列内容，不能只给相对目录或角色名称：
  - MDF_ROOT、owner 路径及分支、角色绝对 worktree、预期完整分支名。
  - Git common dir、设计提交、对应 intent、读写边界与完成证据。

| subagent | 必须使用的路径与分支 | 写入职责 |
| --- | --- | --- |
| write-tests | `worktrees.qa` 项的 path/branch（index 1 如 `qa/feature/<slug>`） | 测试、配置及阶段证据 |
| implement | `worktrees.dev` 项的 path/branch（index 1 如 `dev/feature/<slug>`） | 实现及阶段证据 |
| code-review 的审查者 | owner 的同一绝对路径与固定 review_head | 只读，不建立角色 worktree |

主 Agent 分派前和 subagent 首次操作时都运行内部 CLI：

- `worktree-check --repo <角色绝对路径> --owner <owner绝对路径> --role <qa|dev> [--index N]`。
- 脚本核对 Git 根、完整分支名、worktree 清单绑定与 Git common dir；不匹配则停止，不写入。
- 角色依原 intent no-ff merge owner 后，追加 `--design-commit <固定设计提交>`
  再检查共同基线与 fingerprint。
- 审查者使用 `--role owner --expected-head <review_head>`，只读验证，不合并或写入。

路径约束：

- 所有命令显式指定该 worktree 的工作目录或 `git -C`，文件写入使用该 worktree 下的绝对路径。
- 不得假设 subagent 继承主 Agent cwd；工具自动分配的其他 worktree 不替代 MDF 角色树。
- 仅 Cursor 主 Agent 可按 `common.md` 调用 `move_agent_to_root`；其他宿主与
  subagent 一律绝对路径绑定，横幅随绑定的 worktree/branch 更新。
- 不能绑定并验证指定路径时停止，不在默认目录开工。
- 审查者验证 owner 与 review_head，不合并或写入。

### 等待、交接与收口

等待：

- 主 Agent 等待所有已派阶段完成或明确阻塞，不在任一路仍运行时执行 converge 或删除角色 worktree。
- 一条失败时保留另一条已完成产物；如需修改共同设计，先暂停所有仍在写入的执行者。

交接：

- 各路交接报告实际绝对路径、分支、最终提交 hash、验证/自检结果及未解决项。
- 主 Agent 对各路再次调用同一 worktree-check，传入固定设计提交并追加 `--handoff`。
  - 脚本检查 clean、共同设计，以及 tests（qa）或 implementation（dev）内容是否已提交。
  - ❌ 不以 gate 文件是否存在判定阶段完成。
- 失败保留现场，不以 subagent 的“完成”摘要替代检查；全部交接通过后返回 2 进入 converge。
  - owner 在进入 converge 前确认 write-tests / implement 已在 objectives 勾选。
- implement 以未决交回测试争议时由主 Agent 裁定（默认询问用户，auto-pilot 自裁定），
  按裁定续办对应路；改测试按 `delivery-contract.md`「修改与提交权限」取得批准。
- 合并、测试修改批准、worktree 清理均委托 converge 原流程，不手工 cherry-pick 或删除角色来冒充集成。

收口：单阶段结束、审查通过、版本材料写入或提交成功均不等于 deliver 完成。

- 步骤 5 必须取得 finish 的实际成功结果（close-out）。
  - 按分支核对合并、源分支/worktree 清理，以及 release/hotfix 的 tag 和推送。
  - close-out 删除 owner 后改用步骤 1 固定的主 worktree 核对。
- 若 close-out 部分失败，记录已完成操作与未完成项，按其恢复规则交接，不重放已经发生的发布操作。
- 报告本次完成的阶段、验证、Git 结果或具体阻塞，以及所有仍存活的 subagent 和未完成交接。
- 上下文恢复时用上述现有产物与实际 Git 状态重新核验，不依赖未落地的内存完成标志。
