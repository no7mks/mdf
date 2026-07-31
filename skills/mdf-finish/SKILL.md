---
name: mdf-finish
description: >-
  仅在用户显式调用时，按当前 Gitflow feature、bugfix、release 或 hotfix
  分支完成 Mars Docs Flow 收口。
disable-model-invocation: true
---

# MDF Finish

只在用户显式调用 `$mdf-finish` 时运行。不要因代码完成、测试通过、分支合并或定时任务隐式触发；不要自动 commit。

## 共同前置

1. 本次 outer workflow 开始前要求 clean worktree。按 `mdf-core` 的“入口 Skill 解析 Core”规则验证数字
    V2 Core，运行 `doctor` 与 `branch`。manifest 非 `ready`、detached HEAD、非 Gitflow 分支
   或 dirty worktree 均停止。
2. 当前分支必须是 `feature/*`、`bugfix/*`、`release/<semver>` 或 `hotfix/<semver>`。用户在成功后自
   行复查并 commit；下一次 MDF 入口开始前必须再次 clean。
3. 委托 `$mdf-audit`：release 使用 release audit；feature、bugfix、hotfix 使用 change
   audit。审计必须在本次 outer workflow 的任何写入前开始。

## Feature / Bugfix

1. change audit 先在 clean 基线上形成事实修复计划；无法在本次收口解决的 finding 立即停止且不写入。
2. 在仍 clean 时使用 Core 消歧并移动 planning 目录：

   ```bash
   python3 "$MDF_CORE_SCRIPT" planning-candidates \
     --repo "$REPO_ROOT" --branch-slug "$BRANCH_SLUG"
   ```

   `unique` 时运行 `move-change --source ... --branch-slug ...`；`none` 时创建最小 Change
 目录；`ambiguous` 时停止并请用户消歧。用户要求时才使用 `--dry-run`。
3. 移动后写入审计计划中的当前事实修复，并生成或更新 `changes/unreleased/<slug>/CHANGE.md`。记录实际
   Requirement、Bug outcome、ADR、release notes、breaking、evidence 与已验证的
   Result/Current Docs Updated/Migration/Known Deviations。
4. 复读最终写入内容并对照审计证据，运行 targeted validation；零 finding 后报告 change audit 结构化摘要。对象保持
   `ready`，不创建版本目录、CHANGELOG 或 closeout 根文件。

## Release / Hotfix

1. release audit 或 change audit 有 finding 时，可写入明确的事实修复，但必须停止：不得在同一轮调用
   `release-closeout`。用户手动 commit 后，从 clean 基线重新调用 `$mdf-finish`。
2. 零 finding 时，从审计摘要生成非空简短 `summary`，组装 semantic attestation：
   `semantic: "passed"`、`finding_count: 0`、`summary`；禁止 `waivers`。
3. release 读取全部 unreleased child Change；hotfix 要求该目录为空，并通过
   `--hotfix-change-json` 传入实际结果。Bug outcome 与 major 接受信息保持 Core 既有门禁。
4. 调用：

   ```bash
   python3 "$MDF_CORE_SCRIPT" release-closeout \
     --repo "$REPO_ROOT" \
     --release-date YYYY-MM-DD \
     --semantic-attestation-json \
     '{"semantic":"passed","finding_count":0,"summary":"..."}' \
     [--closures-json '...'] \
     [--deferred-acceptance-json '...'] \
     [--hotfix-change-json '...']
   ```

   用户要求预览时附加 `--dry-run`。preview 不执行验证命令；apply 仍要求 Core 写入前及命令后 worktree clean。失
败时保留现场。

## Bug Outcome 门禁

- `fixed`：关闭 Bug，写 `fixed_in: <version>`；sentinel `found_in` 改为版本。
- `closed`：只允许 `wont-fix`、`not-a-bug`、`cannot-reproduce`、`obsolete`；不写 fixed-in。
- `deferred`：保持 ready、不写 resolution/fixed-in、不归档；sentinel found-in 仍提升。
- critical 只能 fixed；major 的 deferred/wont-fix 必须取得用户明确接受、理由和 follow-up；duplicate
   不进入 outcome。

版本级记录只使用 `changes/<version>/CHANGE.md`；不要创建 `RELEASE.md`、仓库外 spec 或 closeout
YAML。
