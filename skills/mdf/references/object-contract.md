# 工作对象与 Change Schema

本文只定义 Proposal、Bug 和 Change 的持久化 schema、允许值与对象间不变量。
创建、评审、状态转换、版本收口和归档的时机与步骤由各工作流定义。

## Proposal

Proposal 使用 Markdown + YAML frontmatter：id、type: proposal、status、depends_on。
可选属性 `milestone` 为单个非空字符串，表示用户确定的阶段归属；无归属时省略整个字段，
不得写 `milestone: null`、空字符串或列表。同一 milestone 使用相同值。
它仅用于分组，不影响依赖、开工条件或状态流转，不根据组内 PRP 状态自动宣告阶段达成。
不要求独立 milestone 对象；阶段目标及其是否为 MVP 由用户实践决定。
状态为 draft、ready、implemented、released、rejected、replaced。
正常路径 draft → ready → implemented → released；implemented 表示验收后合入 develop，
released 必须记录稳定 SemVer released_in。其他状态不得使用 released_in。
rejected 必须有 reject-reason: wont-do/obsolete/duplicate；duplicate 还须有 duplicate_of，
直接指向同类型的 canonical 非 duplicate PRP，不允许自指或重复链。
replaced 必须有至少两个唯一 replaced_by ID；替代关系不得缺失、自指或成环。
不使用持久化 resolution。released、rejected、replaced 可以归档，implemented 不归档。

依赖 depends_on 为唯一的直接 PRP ID 列表；允许 draft、ready、implemented、released，
其中 implemented/released 已满足依赖。禁止重复、自指、循环、缺失、跨类型及其他终态。
拆分必须同时改写所有原下游引用；replaced 不表示依赖已满足。

Proposal、Bug 和 Jot 的 ID 为前缀后接四位字符，每位取自大写英文（排除 I、O）与数字 2 至 9。
一般关联只写正文；上述重复与替代字段是明确的结构关系。
正文必须含“问题”“期望结果”“范围”“验收标准”四个非空章节；“范围”含“包含”“不包含”非空三级子节。

## Bug

Bug frontmatter 至少包含：

```yaml
id: bug-<4 位字符>
type: bug
status: open
severity: critical | major | trivial
found_in: unreleased | <stable-semver>
```

Bug 不使用 `depends_on`。一般关联只在正文中说明。正文必须包含“观察到的行为”
“期望行为”“复现步骤”“影响”和“所需回归证据”。

`found_in: unreleased` 表示当前未发布线中的稳定关联；它不是 SemVer。`fixed_in`
只接受稳定 SemVer。

Bug 的 `status` 只允许 `open`、`fixed`、`closed`、`rejected`。`open` 表示待修复；
`fixed` 表示已修复、等待独立验证；只有二次验证通过才转为 `closed`。`rejected` 是
终态，且必须有 `reject-reason`：`wont-fix`、`not-a-bug`、`cannot-reproduce`、
`obsolete` 或 `duplicate`。非 duplicate 的 `open`、`fixed`、`closed` Bug 必须有
`critical`、`major` 或 `trivial` 三值 severity。`fixed_in` 只允许在 `closed` Bug 中，
且必须是稳定 SemVer。

duplicate 是被拒绝的 Bug：

```yaml
status: rejected
reject-reason: duplicate
duplicate_of: bug-<canonical>
```

`duplicate_of` 只能直接指向 canonical、非 duplicate Bug；禁止自指和链式
duplicate。duplicate 不需要 `found_in`/`fixed_in`，也不得出现在 Change 的
`fixed`、`closed` 或 `deferred` 中。canonical 与其 duplicate 子项构成一个 group。

## Change

未版本化的子 Change 位于 `docs/changes/unreleased/<slug>/CHANGE.md`：

```yaml
change_kind: feature | bugfix
source_branch: feature/<slug> | bugfix/<slug>
proposals: [prp-...]
fixed: [bug-...]
closed: [bug-...]
deferred: [bug-...]
adrs: [adr-0001]
release_notes: none | {Added/Changed/Deprecated/Removed/Fixed/Security: [text]}
breaking: false
evidence:
  tests: []
  commands: []
  artifacts: []
```

一个 Bug 只能出现在三个 outcome 列表之一。`closed` 只存 `rejected` Bug 的 ID；
拒绝原因由该 Bug 的 `reject-reason` 声明。duplicate ID 不得出现在任何 outcome 列表。

`evidence.tests`、`evidence.commands` 与 `evidence.artifacts` 都是列表；每个元素
必须是非空字符串。

正文必须包含“结果”“已更新的当前文档”和“已知偏差”章节。

## 版本根 Change

`docs/changes/<version>/CHANGE.md` 包含 `change_kind: release|hotfix`、`source_branch`、
`version`、`previous_version`、`included_changes`、Proposal/Bug outcomes、release
notes、`evidence`、审阅记录，以及“结果”“包含的 Change”“收口结果”“found-in 转换”、
“SemVer 决策”“审计”“验证命令”等章节。每个稳定版本只有一个版本根 Change。
