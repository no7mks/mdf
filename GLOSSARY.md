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

一次交付在 start 时冻结的参与人数：`qa`、`dev`、`reviewers`。owner 恒为 1，
不计入可选人数。feature 默认 `1,1,3`，其他 kind 默认 `0,0,3`；四种 kind 都可改。
qa 与 dev 只能同时为 0 或都 ≥1；一侧为 0 则抬成 1。`0,0` 时测试与实现都在
owner 上做；`≥1` 时各有角色 worktree。同侧 ≥2 时并行互不知情，owner 选 base
由该路吸收其余优点，converge 只合 winner。reviewers 是 code-review 并发人数。

## Auto-pilot

`$mdf deliver --auto-pilot` 的持续交付模式：主 Agent 自行裁定原需用户确认的步骤，
仅在 finish 的 Gitflow 收口（合入目标主线并删除源 worktree）前停住确认；
不可恢复的死硬阻塞仍停止。

## ADR

Architecture Decision Record；记录重要且已决定的长期架构取舍。文件为
`docs/adr/<slug>.md`，ID 为 `adr-<slug>`；按主题打开，不编号。

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

UT 为单元测试，PT 为属性测试，E2E 为端到端测试；是否需要及失败标准由项目配置和设计约定。
Code smell 指提示维护性或设计问题的代码特征，由 code-review 判断是否需要在当前范围修复。
