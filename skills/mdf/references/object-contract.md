# 工作对象与 Change Schema

本文只定义 Proposal、Bug 和 Change 的持久化 schema、允许值与对象间不变量。
创建、评审、状态转换、版本收口和归档的时机与步骤由各工作流定义。

## Proposal

Proposal 使用 Markdown + YAML frontmatter：`id`、`type: proposal`、`status`、
`depends_on`。状态只允许 `draft`、`ready`、`closed`。`depends_on` 是当前
Proposal 的直接依赖列表，只能包含其他 `draft`、`ready` 或
`closed + fulfilled` Proposal 的 ID；不得包含重复、自指、循环、Bug、ADR、
缺失对象或其他终态 Proposal。一般关联只在正文中说明，不使用关系 metadata。

正文必须包含 Problem、Desired Outcome、Scope、Acceptance Criteria 四个非空章节；
Scope 必须含非空的 `### In` 与 `### Out` 子节。

合法 Proposal resolution：`fulfilled`（必须写稳定 SemVer `fulfilled_in`）、
`rejected`、`obsolete`、`duplicate`；非 `fulfilled` 不得写 `fulfilled_in`。

## Bug

Bug frontmatter 至少包含：

```yaml
id: bug-<ulid>
type: bug
status: ready
severity: critical | major | trivial
found_in: unreleased | <stable-semver>
```

Bug 不使用 `depends_on`。一般关联只在正文中说明。正文必须包含
Observed Behavior、Expected Behavior、Reproduction、Impact 和
Regression Evidence Required。

`found_in: unreleased` 表示当前未发布线中的稳定关联；它不是 SemVer。`fixed_in`
只接受稳定 SemVer。

非 duplicate 的 active Bug（`draft`/`ready`）必须有 `critical`、`major` 或
`trivial` 三值 severity。

合法 Bug resolution：`fixed`、`wont-fix`、`not-a-bug`、`cannot-reproduce`、
`obsolete`、`duplicate`。非 fixed resolution 不写 `fixed_in`。

duplicate 必须是终态：

```yaml
status: closed
resolution: duplicate
duplicate_of: bug-<canonical>
```

`duplicate_of` 只能直接指向 canonical、非 duplicate Bug；禁止自指和链式
duplicate。duplicate 不需要 `found_in`/`fixed_in`，也不得出现在 Change 的
`fixed`、`closed` 或 `deferred` 中。canonical 与其 duplicate 子项构成一个 group。

## Change

未版本化的子 Change 位于 `changes/unreleased/<slug>/CHANGE.md`：

```yaml
change_kind: feature | bugfix
source_branch: feature/<slug> | bugfix/<slug>
proposals: [prp-...]
fixed: [bug-...]
closed: [bug-...]
deferred: [bug-...]
closed_resolutions:
  bug-...: wont-fix
adrs: [adr-0001]
release_notes: none | {Added/Changed/Deprecated/Removed/Fixed/Security: [text]}
breaking: false
evidence:
  tests: []
  commands: []
  artifacts: []
```

一个 Bug 只能出现在三个 outcome 列表之一。`closed` 只存 ID；其 resolution 在
`closed_resolutions` 中声明。duplicate ID 不得出现在任何 outcome 列表。

`evidence.tests`、`evidence.commands` 与 `evidence.artifacts` 都是列表；每个元素
必须是非空字符串。

正文必须包含 Result、Current Docs Updated、Known Deviations。

## 版本根 Change

`changes/<version>/CHANGE.md` 包含 `change_kind: release|hotfix`、`source_branch`、
`version`、`previous_version`、`included_changes`、Proposal/Bug outcomes、release
notes、`evidence`、审阅记录，以及 Result、Included Changes、Closeout Outcomes、
Found-in Transitions、SemVer Decision、Audit、Validation Commands 等章节。每个稳定版本
只有一个版本根 Change。
