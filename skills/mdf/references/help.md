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
| 1 | 解析 | 约束 | 识别裸调用、help 或 help 主题 | 调用形态 | 2 | 停止 |
| 2 | 展示 | 约束 | 按目录或主题原样输出固定正文 | 完整展示 | 结束 | 停止 |

## 术语与数据结构

### 调用与展示

<a id="s1"></a>

**解析**

识别本次调用：

- 裸 `$mdf`、未知调用或 `$mdf help`：展示「目录」
- `$mdf help <intent>`：展示「主题」中对应条目
- 主题名按空格或连字符等价，如 `fact update` 与 `fact-update`

未知主题时先输出一行 `未知 intent：<原文>`，再展示完整「目录」。
不得猜测未列出的 intent。

验收：调用形态唯一。

通过条件：进入展示。异常与交接：材料缺失则停止。

<a id="s2"></a>

**展示**

只输出本文件「目录」或「主题」正文。保留原分组、标题、列表与示例，
不得改写成另一套表，不得补充未写入的命令。主题命中时只输出该条目，
并附一行 `完整目录：$mdf help`。

验收：输出与本文件对应正文一致。

通过条件：结束。异常与交接：正文缺失则停止。

### 目录

主线：`start → design → [write-tests ∥ implement] → converge → review → finish`

#### 起步

- `$mdf bootstrap`：为全新或几乎全新的项目建立 MDF 起点
- `$mdf init`：接入已有项目或调整配置；新项目转入 bootstrap

#### 规划

- `$mdf intake`：将外部想法分诊为 Bug 和/或多个 Proposal
- `$mdf jot`：追加一条未分诊的随手记录
- `$mdf jot promote`：提升一条 Jot 为 Proposal 或 Bug
- `$mdf bug create`：按已确认内容手动创建 open Bug
- `$mdf prp create`：按已确认内容手动创建 draft Proposal
- `$mdf prp review`：修订单个 active Proposal，验证后转为 ready
- `$mdf prp split`：拆分未开工 PRP，并完整改写依赖
- `$mdf clarify <议题>`：逐题压力测试计划、决策或想法

#### 交付

- `$mdf next [--depth N]`：续办在途流程；无在途时展示 PRP 蓝图
- `$mdf start`：按 Gitflow 创建本地交付分支；始终在
  `<repo-name>-worktrees/` 下建立 worktree
- `$mdf design`：确认设计、测试策略和共享代码底座
- `$mdf write-tests`：按目标编写测试用例
- `$mdf implement`：按已确认设计实现
- `$mdf converge`：集成并持续修复到全量验证通过
- `$mdf review`：审查并修复实现、测试和 code smell
- `$mdf fact update`：同步当前事实；finish 前段自动调用
- `$mdf finish`：按 Gitflow 分支完成审计与收口

#### 维护

- `$mdf archive`：归档终态 Proposal 及 closed/rejected Bug
- `$mdf fact audit`：审阅文档与实现的覆盖、证据和语义
- `$mdf codewiki generate`：用 CodeWiki MCP 新建仓库结构 Wiki
- `$mdf codewiki update`：增量更新符合契约的结构 Wiki
- `$mdf upgrade`：从上游拉取最新 Skill，替换已安装副本并更新 `AGENTS.md` 托管区块
- `$mdf help`：展示本目录
- `$mdf help <intent>`：展示该 intent 的用法要点

#### 示例

```text
$mdf help
$mdf help start
$mdf bootstrap
$mdf init
$mdf next
$mdf next --depth 2
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
$mdf review
$mdf fact update
$mdf finish
$mdf fact audit
$mdf archive
$mdf prp split
$mdf codewiki generate
$mdf codewiki update
$mdf upgrade
$mdf clarify 要不要把缓存放到 Redis
```

### 主题

主题键：`bootstrap`、`init`、`intake`、`jot`、`jot promote`、`bug create`、
`prp create`、`prp review`、`prp split`、`clarify`、`next`、`start`、
`design`、`write-tests`、`implement`、`converge`、`review`、`fact update`、
`finish`、`archive`、`fact audit`、`codewiki generate`、`codewiki update`、
`upgrade`、`help`。

`$mdf bootstrap`
用法：`$mdf bootstrap`
用途：为全新或几乎全新的项目建立 MDF 起点。
说明：不搭建业务工程或测试；已有实现时停止并提示 init。

`$mdf init`
用法：`$mdf init`
用途：接入已有项目或调整 MDF 配置。
说明：新项目自动转入 bootstrap；校验通过并确认后进入 ready。

`$mdf intake`
用法：`$mdf intake`
用途：将外部想法或临时来源分诊为 Bug 和/或多个 Proposal。
说明：必填事实未确认时不写入对象。

`$mdf jot`
用法：`$mdf jot`
用途：追加一条未分诊的随手记录到 `docs/JOTS.md`。
说明：Jot 不是 Proposal、Bug 或 Change。

`$mdf jot promote`
用法：`$mdf jot promote`
用途：提升一条既有 Jot 为 Proposal 或 Bug，并移除原条目。
说明：同一份待提交改动中完成提升与删除。

`$mdf bug create`
用法：`$mdf bug create`
用途：按已确认内容手动创建一个 open Bug。
说明：一次只创建一个对象；外部来源应走 intake。

`$mdf prp create`
用法：`$mdf prp create`
用途：按已确认内容手动创建一个 draft Proposal。
说明：一次只创建一个对象；随后需 `$mdf prp review`。

`$mdf prp review`
用法：`$mdf prp review`
用途：修订单个 active Proposal，验证后转为 ready。
说明：终态或 archive 中的 Proposal 拒绝修改。

`$mdf prp split`
用法：`$mdf prp split`
用途：拆分未开工 PRP，并完整改写依赖。
说明：不拆已开工交付。

`$mdf clarify <议题>`
用法：`$mdf clarify <议题>`
用途：逐题压力测试计划、决策或想法。
说明：议题不能为空；不要求 Git 仓库。

`$mdf next [--depth N]`
用法：`$mdf next` 或 `$mdf next --depth N`
用途：续办在途流程；无在途时展示 ready PRP 蓝图。
说明：深度省略时默认 3；一次只续办一个所选 intent。

`$mdf start`
用法：`$mdf start`
用途：按 Gitflow 创建本地交付分支。
说明：始终从基线在仓库同级 `<repo-name>-worktrees/` 下建立 worktree，
不在当前目录开分支，不 push。feature 同时建立 qa/dev 角色树。

`$mdf design`
用法：`$mdf design`
用途：确认设计、测试策略和共享代码底座。
说明：结束前必须提交 write-tests 与 implement 共用的代码底座。

`$mdf write-tests`
用法：`$mdf write-tests`
用途：按目标编写测试用例。
说明：可与 implement 并行；切到已有 qa worktree，先 merge owner。

`$mdf implement`
用法：`$mdf implement`
用途：按已确认设计实现。
说明：不要求测试先完成；切到已有 dev worktree，先 merge owner。

`$mdf converge`
用法：`$mdf converge`
用途：集成并持续修复到全量验证通过。
说明：修复实现直到项目全部验证项通过。

`$mdf review`
用法：`$mdf review`
用途：审查并修复实现、测试和 code smell。
说明：位于 converge 之后、finish 之前。

`$mdf fact update`
用法：`$mdf fact update`
用途：同步当前事实并委托事实审阅。
说明：finish 前段自动调用；独立调用须 manifest ready。

`$mdf finish`
用法：`$mdf finish`
用途：按 Gitflow 分支完成审计与收口。
说明：提交不代替用户确认或验收。

`$mdf archive`
用法：`$mdf archive`
用途：归档终态 Proposal 及 closed/rejected Bug。
说明：默认预览；确认后再实际归档。

`$mdf fact audit`
用法：`$mdf fact audit`
用途：审阅当前文档与实现的覆盖、证据和语义。
说明：只读；不执行 verification.commands。

`$mdf codewiki generate`
用法：`$mdf codewiki generate`
用途：用 CodeWiki MCP 新建仓库结构 Wiki。
说明：仅写入 `docs/repowiki/`。

`$mdf codewiki update`
用法：`$mdf codewiki update`
用途：增量更新符合 MDF 契约的结构 Wiki。
说明：无结构变化时可报告无更新。

`$mdf upgrade`
用法：`$mdf upgrade`
用途：从上游默认分支拉取最新 Skill 并替换已安装副本。
说明：先预览新旧基线及自当前基线以来触及 Skill 的提交，确认后再替换；更新已有
`AGENTS.md` 托管区块，不改 `.mdf/` 与 `docs/`。替换后在当前分支提交本次路径，
不 push。随后重读新 Skill，同会话后续调用按新副本执行。

`$mdf help`
用法：`$mdf help` 或 `$mdf help <intent>`
用途：展示意图目录或单条用法要点。
说明：不检查仓库、不写入；未知主题时回退到完整目录。
