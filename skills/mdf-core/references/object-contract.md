# 工作对象与 Change Schema

## Requirement

Requirement 使用 Markdown + YAML frontmatter：`id`、`type: requirement`、`status`、
`related`。状态只有 `draft`、`ready`、`closed`；Requirement 在 feature/bugfix finish 后仍为
`ready`，release/hotfix closeout 才能关闭。

正文必须包含 Problem、Desired Outcome、Scope、Acceptance Criteria 四个非空章节；Scope 必须含非空的
`### In` 与 `### Out` 子节。

合法 Requirement resolution：`fulfilled`（必须写稳定 SemVer `fulfilled_in`）、`rejected`、
`obsolete`、`duplicate`；非 `fulfilled` 不得写 `fulfilled_in`。closeout 把 Change 声明的
Requirement 收口为 `fulfilled`；`rejected`/`obsolete`/`duplicate` 只能经
`--closures-json` 对未写入 child Change 的 ready Requirement 补录，关闭后随本次 closeout 归档。

## Bug

Bug frontmatter 至少包含：

```yaml
id: bug-<ulid>
type: bug
status: ready
severity: critical | major | trivial
found_in: unreleased | <stable-semver>
```

Bug 不使用通用 `related`。正文必须包含 Observed Behavior、Expected Behavior、Reproduction、
Impact 和 Regression Evidence Required。

`found_in: unreleased` 表示当前未发布线中的稳定关联；它不是 SemVer。release/hotfix closeout 处理 Bug
时，如果仍为 `unreleased`，统一改为本次版本；已有稳定值不回写。`fixed_in` 只接受稳定 SemVer。

非 duplicate 的 active Bug（`draft`/`ready`）必须有三值 severity：

| severity | closeout 约束 |
|---|---|
| `critical` | 只能 `fixed`；任何 `closed`/`deferred` 都阻止发布 |
| `major` | deferred/wont-fix 需要用户明确接受、理由和 follow-up |
| `trivial` | 可 deferred/wont-fix，无额外逐项取舍门禁 |

合法 Bug resolution：`fixed`、`wont-fix`、`not-a-bug`、`cannot-reproduce`、`obsolete`、
`duplicate`。非 fixed resolution 不写 `fixed_in`。

closeout 还必须覆盖每一个 `status: ready` 且 `found_in: unreleased` 的 Bug。已有稳定 `found_in`
 的 ready Bug（含历史 deferred）可不进入本次 outcomes。

duplicate 必须是终态：

```yaml
status: closed
resolution: duplicate
duplicate_of: bug-<canonical>
```

`duplicate_of` 只能直接指向 canonical、非 duplicate Bug；禁止自指和链式 duplicate。duplicate 不需要
`found_in`/`fixed_in`，不进入 Change 的 `fixed`、`closed` 或 `deferred`。canonical 与所有
duplicate 子项作为一个 archive group 同时归档。

## Change

feature/bugfix 完成后的 `changes/unreleased/<slug>/CHANGE.md`：

```yaml
change_kind: feature | bugfix
source_branch: feature/<slug> | bugfix/<slug>
requirements: [req-...]
fixed: [bug-...]
closed: [bug-...]
deferred: [bug-...]
closed_resolutions:
  bug-...: wont-fix
adrs: [adr-0001]
release_notes: none | {Added/Changed/Deprecated/Removed/Fixed/Security: [text]}
breaking: false
evidence: {tests: [], commands: [], artifacts: []}
```

一个 Bug 只能出现在三个 outcome 列表之一。`closed` 只存 ID；其 resolution 在 `closed_resolutions` 中
声明。duplicate ID 不得出现在任何 outcome 列表；若实际处理了 duplicate，closeout 阻断并要求改为 canonical
ID。

正文必须包含 Result、Current Docs Updated、Migration、Known Deviations。MDF 在
feature/bugfix finish 时由入口 Skill 生成该文件；用户不需要手写其目录收口流程。Core 不自动 `git commit`。

## 版本根 Change

`changes/<version>/CHANGE.md` 由 release/hotfix closeout 生成，包含
`change_kind: release|hotfix`、`source_branch`、`version`、`previous_version`、
`included_changes`、聚合后的 Requirement/Bug outcomes、release notes、evidence、audit 记录
，以及 Result、Included Changes、Closeout Outcomes、Found-in Transitions、SemVer
Decision、Audit、Validation Commands 等章节。版本根 Change 是唯一的版本级 closeout 记录；不存在
`RELEASE.md`。

release 会移动并保留所有 unreleased child Change；hotfix 不接受任何 unreleased Change，直接生成只有根
`CHANGE.md` 的版本目录。

## Closeout 输入与门禁

`release-closeout` 不读取仓库外 spec 或 inputs。`$mdf-finish` 在一次显式调用中把分支、日期、
`--semantic-attestation-json`、Bug outcome（可经 `--closures-json` 超集补录）和 major 接受信息
交给 Core；验证命令只从 ready manifest 的 `verification.commands` 读取，不在仓库增加 closeout YAML。

- Change 声明的 outcomes 必须被 closures 覆盖；`--closures-json` 可额外补录未写入 child Change 的
  `fixed`/`closed`/`deferred`，或以 `rejected`/`obsolete`/`duplicate` 关闭 ready
  Requirement。
- `verification.commands` 必须是非空字符串列表；closeout preview 不执行它们，apply 在目标仓库执行后必须仍保持
  clean worktree，否则停止且不自动清理。
- preview/apply 都需要 passed、零 finding、非空 `summary` 的
  `--semantic-attestation-json`。语义审计由 `$mdf-finish` 负责并 attestation，Core 不自签语义结果
  。attestation **禁止** `waivers` 字段；summary 会写入版本根 Change 的 Audit 段。
- `fixed` 关闭 Bug 并写 `fixed_in`；`closed` 写终态非 fixed resolution；`deferred` 保持
  `ready`、不写 `resolution`/`fixed_in`，但将 `found_in: unreleased` 提升为版本。deferred
  Bug 不归档。
