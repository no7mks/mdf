---
name: mdf-audit
description: 仅在用户显式调用或 mdf-finish 委托时，按当前 Gitflow 分支执行 release 全审或变更审计。
disable-model-invocation: true
---

# MDF Audit

只在用户显式调用 `$mdf-audit`，或被 `$mdf-finish` 显式委托时执行。审计始终只读：不写入、移动、提交或生成持久报告。

## 共同前置

1. 按 `mdf-core` 的“入口 Skill 解析 Core”规则验证 V2 Core：`info` 的 `protocol_version`、
   `tool_version` 和 `schema_version` 均为数字 `2`。
2. 解析目标 Git 根为 `REPO_ROOT`，运行：

   ```bash
   python3 "$MDF_CORE_SCRIPT" doctor --repo "$REPO_ROOT"
   ```

3. `clean` 必须为 `true`；否则只报告 dirty 状态并停止。manifest 必须为 `ready`；未初始化或
   `initializing` 时只建议显式调用 `$mdf-init-repo`。
4. 运行 `branch --repo`，按当前分支选择审计：`release/<semver>` 为 release audit；`feature/*`、
   `bugfix/*`、`hotfix/<semver>` 为 change audit；其他分支停止。审计开始时记录 HEAD、分支和
   `git status --porcelain`；任一项在审计期间变化时废弃结果并重新开始。

## Change Audit

- feature/bugfix 使用本地 `develop...HEAD`；hotfix 使用本地 `master...HEAD`。基线分支不存在或无法取得
  merge-base 时停止并请用户修复本地 Gitflow 基线。
- 读取 `git diff --name-status "$BASE...HEAD"`，实际检查变更涉及的代码、配置、schema、测试和文档。
- 对每个受影响的当前事实页核对其 evidence；对每个受影响的 evidence 反查相关事实页。检查 Requirement、Bug、Change、
  ADR、Known Deviations 是否准确表达当前检出，且不把计划写成事实。
- 只在变更触及时审阅 ADR、Known Deviations 或未变更的事实页；必须在结果中说明未触及理由。
- 运行 `python3 "$MDF_CORE_SCRIPT" validate --repo "$REPO_ROOT" --scope targeted`，
  保留命令及结果作为确定性验证证据。

## Release Audit

- 要求本地 `develop` 存在，并记录 `develop...HEAD` 作为发布上下文。
- 全量审阅 `CONTEXT.md`、全部 `docs/product/**` 与 `docs/system/**` 当前事实页、全部 ADR，以及本次
  unreleased Change 引用的 Requirement/Bug；逐项核对 evidence、generated 元数据和当前 checkout。
- 运行：

  ```bash
  python3 "$MDF_CORE_SCRIPT" validate --repo "$REPO_ROOT" --scope full
  ```

- 保留所有 Core 确定性 finding，并区分 Core 结论与 Agent 语义判断；任何 unresolved finding 都阻断
  release closeout。不要提供 waiver。

## 结果

返回会话内结构化摘要：`audit_kind`、`base_ref`、`head`、覆盖的代码/证据/文档、未触及理由、findings 与
`semantic`/`finding_count`。只有 `semantic: "passed"`、`finding_count: 0` 的摘要可供
`$mdf-finish` 组装 closeout attestation。

被 `$mdf-finish` 委托时，release/hotfix 的版本根 CHANGE 还必须写入由该摘要压缩出的非空简短 `summary`；Core
不独立验证语义。
