# GLOSSARY.md

## MDF

Mars Development Flow；面向 Git 仓库的版本化文档与交付流程。

## Jot

`docs/JOTS.md` 中尚未分诊的随手记录。它可以是想法、优化、小问题或观察；提升后才成为
Proposal 或 Bug。Jot 不是 Proposal/Bug 的 `draft` 状态，也不是 Change。

## Bug 状态

Bug 使用 `open`、`fixed`、`closed` 或 `rejected`。`fixed` 必须经二次验证后转为
`closed`；`rejected` 是终态，并由 `reject-reason` 记录拒绝原因。

## 当前事实文档

描述当前 checkout 已成立行为，并由仓库内 evidence 支持的文档。

## 基线

`manifest.baselines` 中对当前状态主题的有证据声明。

## 验证命令

`manifest.verification.commands` 中的具名可执行验证项；`kind` 只是标签，
不参与筛选。

## 验证 suite

`manifest.verification.suites` 是 suite 名到验证项 id 列表的映射。`quick` 与
`full` 是两个全局 suite，其余 key 是交付 suite：

- **quick**：always-run，必须声明。日常门禁；通常挂全部 UT 与声明为快速的 IT/e2e。
- **full**：隐含为全部验证项，不得声明。release / hotfix 使用。
- **交付 suite**：覆盖某 feature 的本交付全量（含慢路径）。不是 full，也不是
  「碰巧改到的 quick 文件」。

未分层（manifest 无 `suites`）时，全部项同时属于 quick 与 full。
**quick 复现用例**：非 quick 用例在门禁后失败时，为复现同一缺陷补进 quick 的
用例；原慢用例保留。

## CodeWiki

通过 CodeWiki MCP 生成与更新的仓库结构 Wiki。

## Planning 工作区

唯一的 `planning` 分支与 `<repo-name>-worktrees/planning` worktree，用于
Proposal 的新建、评审、拆分，以及 intake / jot promote 为 Proposal。主 worktree
保持 develop；合入 develop 后 `$mdf start` 才看到新对象。

## Roster

一次交付在 start 时冻结的参与人数与并行策略：`qa`、`dev`、`reviewers`，
以及 `qa_strategy`、`dev_strategy`、`review_strategy`；可选 `models`。
owner 恒为 1，不计入可选人数。可用 `--roster` 展开命名组合（不写入材料）：
`solo` 为 `0,0,1`；`min-tdd` 为 `1,1,2` + best-of-n；`competing-pair` 为
`2,2,3` + best-of-n；`coop-pair` 为 `2,2,3` + partition。feature 默认
`min-tdd`，其他 kind 默认 `solo`。细项可覆盖展开结果。qa 与 dev 只能同时
为 0 或都 ≥1；一侧为 0 则抬成 1。`0,0` 时测试与实现都在 owner 上做；`≥1`
时各有角色 worktree。
qa/dev 默认 `best-of-n`：同侧 ≥2 时并行互不知情，owner 选 base 由该路吸收
其余优点，converge 只合 winner。`partition`：design 派发切片，converge 按
index 全部合入。review 默认 `replicate`（每人覆盖同一份本轮范围），可选
`partition`（切片审查）；owner 汇总裁定，不按票数。`models` 按 intent 可选
配置，键只允许 `write-tests`、`implement`、`code-review`。值为一句口语描述，
可点名一个或多个模型，不要求官方 id。Agent 分派该 intent 时现场解析并选用；
该路有多名执行者时可把多个模型分给他们。省略该键则该路不讨论模型。reviewers
是 code-review 并发人数。

## Auto-pilot

`$mdf deliver --auto-pilot` 的持续交付模式：主 Agent 自行裁定原需用户确认的步骤，
仅在 finish 的 Gitflow 收口（合入目标主线并删除源 worktree）前停住确认；
不可恢复的死硬阻塞仍停止。

## ADR

Architecture Decision Record；记录重要且已决定的长期架构取舍及其理由，不描述
当前结构。文件为 `docs/context/adr/<slug>.md`，ID 为 `adr-<slug>`；按主题打开，
不编号。

## 路由页与主题叶

路由页只做边界与链接（`docs/README.md`、`docs/user-guide/README.md`、
`docs/system/overview.md`、切面 `index.md`）；主题叶是某一主题当前事实的唯一
归属页，独立可加载。`docs/README.md` 是维护者文档入口，按要找的主题打开一份
页面，不是阅读清单，也不是 Proposal、Bug 的工作清单。

## 唯一归属

一条可观察契约只写在一份主题叶；其他页面只链接，不复述。

## 加载质量

fact audit 对文档结构的语义审阅：入口不过载、路由页只路由、唯一归属、主题拆页、
读者分离、ADR 不复述当前结构、overview 核心模块表。行数硬限制由 CLI 检查
（`size.hard`）；整份 `AGENTS.md` 超过 200 行为 warning `agents.size`。

## Proposal 状态

draft 为待评审，ready 为可交付，implemented 为已验收合入 develop，released 为已发布。
rejected 用 reject-reason 说明不实施原因；replaced 表示需求已由拆分出的 PRP 承接。

## Milestone 与 MVP

Milestone（里程碑）表示用户定义的阶段目标；PRP 的可选 `milestone` 属性记录阶段归属。
`depends_on` 可引用 milestone 值，表示该阶段下已无 draft 或 ready PRP。
MVP（最小可行产品）是满足最小可用或验证目的的产品范围，可作为 milestone 的目标，
不由 PRP 数量或实施顺序自动决定。

## Objectives、Gate 与收敛

objectives 是本次交付目标与验收约束，引用 PRP。Gate 是基于产物、内容指纹、验证与语义审查的阶段门禁。
write-tests 完成条件是测试已编写且可编译或可加载执行，不要求全绿。
converge（收敛）集成测试和实现，持续修复实现直到**当前交付所需 suite**通过。
「全绿」相对该 suite，不等于 manifest 里每一条命令。

## 测试类别与 Code Smell

UT 为单元测试，PT 为属性测试，IT 为集成测试，E2E 为端到端测试；是否需要及失败标准由 `docs/system/testing/` 与设计约定。
Code smell 指提示维护性或设计问题的代码特征，由 code-review 判断是否需要在当前范围修复。
