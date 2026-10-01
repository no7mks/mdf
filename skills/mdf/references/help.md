# Help

`$mdf help` 展示完整目录；`$mdf help <intent>` 展示该条用法要点。
裸 `$mdf` 与未知调用按本流程执行。不读取其他 intent、不检查仓库、不写入。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Parse call                     │
└────────────────┬─────────────────┘
                 │
                 ├──── 材料缺失 ────→ [停止]
                 │
                 ▼ 调用可解析
┌──────────────────────────────────┐
│ 2 Render output                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

不读取 `references/` 中的其他流程，不调用 CLI，不解析 Git 根。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Parse call | 约束 | 识别裸调用、help 或 help 主题 | 调用形态 | 2 | 停止 |
| 2 | Render output | 约束 | 按目录或主题原样输出固定正文 | 完整展示 | 结束 | 停止 |

## 术语与数据结构

### 调用与展示

<a id="s1"></a>

**解析**

识别本次调用：

- 裸 `$mdf`、未知调用或 `$mdf help`：展示「目录」
- `$mdf help <intent>`：展示「主题」中对应条目
- 主题名按空格或连字符等价，如 `fact update` 与 `fact-update`；
  `tree`、`prp tree`、`next?` 与 `next？` 等价

未知主题时先输出一行 `未知 intent：<原文>`，再展示完整「目录」。
不得猜测未列出的 intent。

验收：调用形态唯一。

通过条件：进入展示。异常与交接：本文件「目录」或「主题」正文缺失则停止。

<a id="s2"></a>

**展示**

只输出本文件「目录」或「主题」正文。保留原分组、标题、列表与示例，
不得改写成另一套表，不得补充未写入的命令。主题命中时只输出该条目，
并附一行 `完整目录：$mdf help`。

验收：输出与本文件对应正文一致。

通过条件：结束。异常与交接：正文缺失则停止。

### 目录

主线：`start → [design?] → work → converge → code-review → verify full → fact audit → close-out`

#### 起步

- `$mdf bootstrap`：为全新或几乎全新的项目建立 MDF 起点
- `$mdf init`：接入已有项目或调整配置；新项目转入 bootstrap，已有项目转入 migrate
- `$mdf init migrate`：将已有项目材料与布局收敛到当前结构；也可 `$mdf migrate`

#### 规划

- `$mdf intake`：将外部想法分诊为 Bug 和/或多个 Proposal
- `$mdf jot`：追加一条未分诊的随手记录
- `$mdf jot promote`：提升一条 Jot 为 Proposal 或 Bug
- `$mdf bug create`：按已确认内容手动创建 open Bug
- `$mdf prp create`：按已确认内容手动创建 draft Proposal
- `$mdf prp review`：修订单个 active Proposal，验证后转为 ready
- `$mdf prp split`：拆分未开工 PRP，并完整改写依赖
- `$mdf tree [--depth N]`：按 milestone 分组画出 draft/ready PRP 依赖树；也可
  `$mdf prp tree` 或 `$mdf next?`
- `$mdf clarify <议题>`：压力测试计划、决策或想法

#### 交付

- `$mdf next [--depth N]`：续办在途（四种 kind 共用主线）；无在途时委托 tree
- `$mdf deliver [<target>] [--auto-pilot] [--yolo]`：从 start 起持续推进到 close-out；可并行阶段强制 subagent 分别执行
- `$mdf start`：按 Gitflow 创建本地交付分支；始终在
  `<repo-name>-worktrees/` 下建立 worktree
- `$mdf design`：确认设计、测试策略和共享代码底座
- `$mdf write-tests`：按目标编写可执行测试；不要求全绿
- `$mdf implement`：按已确认设计实现
- `$mdf converge`：objectives + on-site，循环到达成
- `$mdf fix <bug-id> [--yolo]`：先确认 failing test，再修复并标为 fixed
- `$mdf verify-fix [<bug-id>]`：二次验证已 fixed 的 Bug（复现用例 + 仅审该修复）
- `$mdf verify --level on-site|full`：module 级验证；converge 用 on-site，主链在
  code-review 后跑 full
- `$mdf code-review`：审查并修复；收口为无 commit 的 `code-review.md` 终稿（非 gate）
- `$mdf fact update [<path>...] [--scope branch|full|paths]`：按实现对齐当前事实，再修范围内结构；
  主链在 verify full 之后、必要时于 fact audit 前调用
- `$mdf close-out` / `$mdf finish`：材料与 Gitflow 收口（不含 verify full / fact）

#### 维护

- `$mdf archive`：归档终态 Proposal 及 closed/rejected Bug
- `$mdf fact audit [<path>...] [--scope branch|full|paths]`：只读审阅覆盖、证据、语义与文档结构；
  主链在 verify full 之后、close-out 之前
- `$mdf prettify [<path>...] [--scope branch|full|paths]`：把文档改写为列表、表格与图，不改语义
- `$mdf codewiki generate`：用 CodeWiki MCP 新建仓库结构 Wiki
- `$mdf codewiki update`：增量更新符合契约的结构 Wiki
- `$mdf upgrade [--source <url>]`：从上游替换已安装 Skill 与 `AGENTS.md` 托管区块
- `$mdf to <target>`：进 worktree（`plan`/`develop`/`deploy`）
- `$mdf sync`：先拉后推三大 trunk；其他分支只报告
- `$mdf integrate`：同仓验收；跨仓才收发消息
- `$mdf help` / `$mdf help <intent>`：目录或单条用法

#### 示例

```text
$mdf help
$mdf help start
$mdf bootstrap
$mdf init
$mdf init migrate
$mdf migrate
$mdf next
$mdf next?
$mdf next --depth 2
$mdf tree
$mdf prp tree
$mdf tree --depth 2
$mdf deliver
$mdf deliver prp-001
$mdf deliver bug-CD34 --auto-pilot
$mdf deliver --auto-pilot
$mdf deliver --yolo
$mdf start
$mdf jot
$mdf jot promote
$mdf intake
$mdf bug create
$mdf prp create
$mdf prp review
$mdf design
$mdf write-tests
$mdf implement
$mdf converge
$mdf fix bug-CD34
$mdf fix bug-CD34 --yolo
$mdf verify-fix
$mdf verify-fix bug-CD34
$mdf verify --level on-site
$mdf verify --level full
$mdf code-review
$mdf fact update
$mdf fact update --scope full
$mdf close-out
$mdf finish
$mdf fact audit
$mdf prettify --scope full
$mdf archive
$mdf prp split
$mdf codewiki generate
$mdf codewiki update
$mdf upgrade
$mdf to plan
$mdf to develop
$mdf sync
$mdf integrate
$mdf clarify 要不要把缓存放到 Redis
```
### 主题

主题键：

- 起步：`bootstrap`、`init`、`init migrate`、`migrate`
- 规划：`intake`、`jot`、`jot promote`、`bug create`、`prp create`、`prp review`、`prp split`；
  `tree`、`prp tree`、`clarify`
- 交付：`next`、`deliver`、`start`、`design`、`write-tests`、`implement`、`converge`；
  `fix`、`verify-fix`、`verify`、`code-review`、`fact update`、`fact audit`、`close-out`/`finish`
- 维护：`archive`、`fact audit`、`prettify`、`codewiki generate`、`codewiki update`、`upgrade`；
  `to`、`sync`、`integrate`、`help`

- `$mdf bootstrap`
  - 用法：`$mdf bootstrap`
  - 用途：为全新或几乎全新的项目建立 MDF 起点。
  - 说明：不搭建业务工程或测试；已有实现时停止并提示 migrate。

- `$mdf init`
  - 用法：`$mdf init`
  - 用途：接入已有项目或调整 MDF 配置。
  - 说明：新项目转入 bootstrap，已有项目转入 migrate。

- `$mdf init migrate`
  - 用法：`$mdf init migrate` 或 `$mdf migrate`
  - 用途：将已有项目材料与布局收敛到当前 MDF 结构。
  - 说明：init 的子 intent；也可由 `$mdf init` 内部委托；新项目停止并提示 bootstrap。

- `$mdf migrate`
  - 用法：`$mdf migrate` 或 `$mdf init migrate`
  - 用途：将已有项目材料与布局收敛到当前 MDF 结构。
  - 说明：与 `$mdf init migrate` 相同；新项目停止并提示 bootstrap。

- `$mdf intake`
  - 用法：`$mdf intake`
  - 用途：将外部想法或临时来源分诊为 Bug 和/或多个 Proposal。
  - 说明：在 planning 工作区写入；必填事实未确认时不写入对象。

- `$mdf jot`
  - 用法：`$mdf jot`
  - 用途：追加一条未分诊的随手记录到 `docs/JOTS.md`。
  - 说明：Jot 不是 Proposal、Bug 或 Change。

- `$mdf jot promote`
  - 用法：`$mdf jot promote`
  - 用途：提升一条既有 Jot 为 Proposal 或 Bug，并移除原条目。
  - 说明：同一份待提交改动中完成提升与删除；提升为 Proposal 时在 planning 工作区进行。

- `$mdf bug create`
  - 用法：`$mdf bug create`
  - 用途：按已确认内容手动创建一个 open Bug。
  - 说明：一次只创建一个对象；外部来源应走 intake。不要求 doctor 零 finding。

- `$mdf prp create`
  - 用法：`$mdf prp create`
  - 用途：按已确认内容手动创建一个 draft Proposal。
  - 说明：一次只创建一个对象；须在 planning 工作区创建并合入 develop；随后需 `$mdf prp review`。

- `$mdf prp review`
  - 用法：`$mdf prp review`
  - 用途：修订单个 active Proposal，验证后转为 ready。
  - 说明：在 planning 工作区修订；终态或 archive 中的 Proposal 拒绝修改。

- `$mdf prp split`
  - 用法：`$mdf prp split`
  - 用途：拆分未开工 PRP，并完整改写依赖。
  - 说明：不拆已开工交付；须在 planning 工作区拆分并合入 develop。

- `$mdf clarify <议题>`
  - 用法：`$mdf clarify <议题>`
  - 用途：压力测试计划、决策或想法。
  - 说明：议题不能为空；不要求 Git 仓库。

- `$mdf tree [--depth N]`
  - 用法：`$mdf tree`、`$mdf prp tree`、`$mdf next?` 或 `$mdf tree --depth N`
  - 用途：画出按 milestone 分组的 draft/ready PRP 混态依赖树与索引。
  - 说明：深度省略时默认 3；只读。问号版 next 进入本主题，不是 next。

- `$mdf next [--depth N]`
  - 用法：`$mdf next` 或 `$mdf next --depth N`
  - 用途：续办在途流程；无在途时委托 tree。
  - 说明：深度省略时默认 3，仅在委托 tree 时生效；一次只续办一个所选 intent。
    四种 kind 交付分支续办当前交付主线。`$mdf next?` 见 tree。

- `$mdf deliver [<target>] [--auto-pilot] [--yolo]`
  - 用法：`$mdf deliver`、`$mdf deliver <target>`、`$mdf deliver --auto-pilot` 或 `$mdf deliver --yolo`
  - 用途：锁定当前一次交付，必要时先 start，持续运行到 close-out 完成。
  - 说明：
    - target 为位置参数，自动分辨 PRP 或 Bug；分不清则询问。无 target 时锁定并续办
      当前在途交付；target 冲突或命中已 in_progress 的 Proposal 时停止。
    - 支持 feature/bugfix/hotfix/release；roster ≥1 且两路可并行时强制分别使用
      qa/dev worktree 的 subagent。
    - design 的 Baseline 与 converge 由各 intent 自行派恰好 1 个 owner subagent，不走 deliver 步骤 4。
    - 默认遇到需用户决定或外部阻塞时暂停。
    - `--auto-pilot` 由 Agent 自裁定，仅在 Gitflow 收口（合入目标主线并删除源 worktree）前确认；
      `--yolo` 同等自裁定且跳过该确认；死硬阻塞仍停止。
    - `--roster` 可转交给 start，仅尚未 start 时有效。
    - strategy / models 可转交给 start、design、code-review：
      `--qa-strategy`、`--dev-strategy`、`--review-strategy`；
      `--write-tests-model`、`--implement-model`、`--code-review-model`。
    - 包含 close-out 的合并及适用的 tag、发版推送。

- `$mdf start`
  - 用法：`$mdf start`；可带 `--roster`、`--*-strategy`、`--*-model`
  - 用途：按 Gitflow 创建本地交付分支。
  - 说明：
    - 始终在同级 `<repo-name>-worktrees/` 建 worktree，不在当前目录开分支，不 push。
    - 开分支前确认并冻结 roster（member/strategy/models）；人数 ≥1 时建 qa/dev 角色树。
    - roster 默认：feature=min-tdd；release=solo+3 partition reviewer；其他=solo。
    - release 开分支前确认发布目标（工作线、联调、`has_dev`；checklist 含 integrate；
      不实施新 PRP；无开发则预勾 owner 开发/converge）。
    - bugfix/hotfix 均写 objectives checklist（roster `0,0` 由 start 写入）。

- `$mdf design`
  - 用法：`$mdf design`；可带与 start 相同的 strategy / models 参数
  - 用途：确认设计、测试策略和共享代码底座。
  - 说明：Clarify 在当前会话；Baseline 由本 intent 派恰好 1 个 owner subagent
    写设计与共用代码底座，不计入 roster。partition 时在 design.md 写明各 index 切片。

- `$mdf write-tests`
  - 用法：`$mdf write-tests`
  - 用途：按目标编写测试用例。
  - 说明：可与 implement 并行；roster ≥1 时在 qa worktree 执行，先 merge owner。
    写完可执行测试即完成，不要求全绿。

- `$mdf implement`
  - 用法：`$mdf implement`
  - 用途：按已确认设计实现。
  - 说明：不要求测试先完成；roster ≥1 时在 dev worktree 执行，先 merge owner。

- `$mdf converge`
  - 用法：`$mdf converge`
  - 用途：roster-join（如有）并持续修复到所需 suite 通过。
  - 说明：本 intent 派恰好 1 个 owner subagent 执行合流、验证与记录；
    测改批准回主会话，不计入 roster。修到 lint/build/quick/smoke 与本交付 named suite 通过；不要求 release。

- `$mdf fix <bug-id>`
  - 用法：`$mdf fix <bug-id>` 或 `$mdf fix <bug-id> --yolo`
  - 用途：澄清、确认 failing test、修复并验证一个 open Bug，标为 `fixed`。
  - 说明：
    - 修复前必须有针对该 Bug 的有效红灯；没有就先写测试并确认失败。
    - 不切分支、不 start、不 code-review、不 finish；不标 `closed`。
    - `--yolo` 自裁定 clarify，不跳过红灯；二次验证走 `$mdf verify-fix`。

- `$mdf verify-fix [<bug-id>]`
  - 用法：`$mdf verify-fix` 或 `$mdf verify-fix <bug-id>`
  - 用途：二次验证已 `fixed` 的 Bug（复现用例 + 仅审该修复）。
  - 说明：close-out 关闭前内部委托；不标 `closed`、不写 `fixed_in`、不跑 release。
    无 ID 时只处理当前 release/hotfix 上待收入的 `fixed` Bug。

- `$mdf verify --level on-site|full`
  - 用法：`$mdf verify run --level on-site|full [--module|--paths|--test ...]`
  - 用途：module 级验证；converge/开发用 on-site，主链在 code-review 后跑 full。
  - 说明：full 写 `verify.full.json`（feature/bugfix/hotfix→smoke，release→release；
    不含 commit）；on-site 不落盘，选题经 `--test`。

- `$mdf code-review`
  - 用法：`$mdf code-review`；可带 `--review-strategy` / `--code-review-model`
  - 用途：审查并修复实现、测试和 code smell。
  - 说明：进行中可记 tip；裁定收口后覆盖为无 commit 的 `code-review.md` 终稿（非
    gate）。主链在 converge 后、verify full 前。进度只认 objectives 自勾。
    首轮按 roster.reviewers；后续增量并复核。默认 replicate；partition 按切片派工。

- `$mdf fact update`
  - 用法：`$mdf fact update [<path>...] [--scope branch|full|paths]`
  - 用途：按实现对齐当前事实，再修范围内结构 finding，并委托事实审阅。
  - 说明：独立默认 `branch`；`full` 整理知识面全树。主链只用 branch/paths；
    release `--base` 为上一正式发布。独立调用须 manifest ready。

- `$mdf close-out` / `$mdf finish`
  - 用法：`$mdf close-out` 或 `$mdf finish`
  - 用途：按 Gitflow 分支完成审计与收口。
  - 说明：提交不代替用户确认；release/hotfix 收入 `fixed` Bug 前委托 `$mdf verify-fix`。
    合入目标主线前可建议 soft-reset squash（见 delivery-contract）；不擅自改写历史。

- `$mdf archive`
  - 用法：`$mdf archive`
  - 用途：归档终态 Proposal 及 closed/rejected Bug。
  - 说明：仅用户要求预览时 dry-run；未要求则实际归档。

- `$mdf fact audit`
  - 用法：`$mdf fact audit [<path>...] [--scope branch|full|paths]`
  - 用途：只读审阅覆盖、证据、语义与加载质量。
  - 说明：不执行 `verification`；`size.hard` 阻断。主链 release `--base` 为上一正式发布。

- `$mdf prettify`
  - 用法：`$mdf prettify [<path>...] [--scope branch|full|paths]`（省略为 branch）
  - 用途：按 `doc-structure.md` 改写为大列表/表格/图，不改语义。
  - 说明：`prose-check` 零违例、validate 无新增 finding 且逐份对照语义后提交。

- `$mdf codewiki generate` / `$mdf codewiki update`
  - 用法：`$mdf codewiki generate` 或 `$mdf codewiki update`
  - 用途：新建或增量更新 `docs/repowiki/` 结构 Wiki。
  - 说明：update 无结构变化时可报告无更新。

- `$mdf upgrade`
  - 用法：`$mdf upgrade [--source <url>]`
  - 用途：从上游替换已安装 Skill 与 `AGENTS.md` 托管区块并提交（不 push），随后重读。
  - 说明：仅不符契约才建议 `$mdf migrate`。

- `$mdf to <target>`
  - 用法：`$mdf to plan|develop|deploy|<分支>`
  - 用途：进入目标 worktree；缺树时建立。不创建新交付分支。
  - 说明：`plan` 进 planning；`develop` 回主树；`deploy` 检出 master 并保留 gitignore config。

- `$mdf sync`
  - 用法：`$mdf sync`；先拉后推三大 trunk，多余分支只报告；禁止 force-push。
- `$mdf integrate`
  - 用法：`$mdf integrate`
  - 用途：同 worktree 保留角色与验收；跨 worktree 才收发消息。强制 Goal，先 courtesy 等 ack。
  - 说明：每分钟 heartbeat；只改本仓、只 poll 本侧。
- `$mdf help`
  - 用法：`$mdf help` 或 `$mdf help <intent>`
  - 用途：展示意图目录或单条用法要点。
  - 说明：不检查仓库、不写入；未知主题时回退到完整目录。
