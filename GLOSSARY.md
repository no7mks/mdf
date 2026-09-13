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

`manifest.verification.commands` 中交付前执行的命令。

## CodeWiki

通过 CodeWiki MCP 生成与更新的仓库结构 Wiki。

## ADR

Architecture Decision Record；记录重要且已决定的长期架构取舍。

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
converge（收敛）集成测试和实现，持续修复实现直到项目全部验证项通过。

## 测试类别与 Code Smell

UT 为单元测试，PT 为属性测试，E2E 为端到端测试；是否需要及失败标准由项目配置和设计约定。
Code smell 指提示维护性或设计问题的代码特征，由 code-review 判断是否需要在当前范围修复。
