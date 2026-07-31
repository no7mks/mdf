# MDF 工作流契约

所有命令均由 `$mdf <command>` 显式调用；内部材料不是独立 Skill。`init-repo` 与
`review-doc` 在需要逐题澄清时使用内部 grill 工作流。每个 outer workflow 开始前
要求 clean worktree；入口可产生改动，但绝不自动
`git commit`，用户须在下一次入口前自行复查并提交。

## init 与 review

- `$mdf init-repo` 先通过内部 grill 工作流收敛八项基线、最近稳定版本和
  `verification.commands`。canonical路径已有内容时必须先展示完整写入方案并取得确认。Core
  `init` 只创建 `initializing` scaffold，不接收验证命令参数。若本次新增或修改
  `CONTEXT.md`、`docs/product/**` 或 `docs/system/**`，入口必须保留
  `initializing`、停止并要求用户复核提交；下一次必须显式重新调用
  `$mdf init-repo`。续办时 full validation 只允许 `manifest.initializing`
  这一项 finding，入口才可写 ready 并再次 full
  validate。既有事实页未改动时可在本次直接完成该步骤。
- `$mdf review-doc` 通过内部 grill 工作流新建或修订一个 active
  Requirement/Bug。既有对象以 canonical
  ID 或路径定位；ready 对象开始评审即转 draft，未确认时保留 draft，确认后才定向验证并转 ready。closed/archived
对象不可在此修改。

## 审计与 feature / bugfix finish

- `$mdf audit`
  在 ready、clean 的支持 Gitflow 分支上运行：release 分支执行 release
  audit；feature、bugfix、hotfix 执行 change audit。change
  audit 以 feature/bugfix 的 `develop...HEAD` 或 hotfix 的 `master...HEAD`
  为范围；release audit 全量核对
  `CONTEXT.md`、产品/系统事实、ADR 与本次 Change 引用的对象。
- feature/bugfix finish 先在 clean 基线上完成 change
  audit 和所有 Core 写前置步骤，再写入可修复的事实更新、复读最终内容、运行 targeted
  validation 并生成
  `changes/unreleased/<slug>/CHANGE.md`。对象保持 ready，不更新 CHANGELOG，不关闭或归档对象。

## release / hotfix finish

一次显式 `$mdf finish`：

1. release 使用 release audit，hotfix 使用 change
   audit；任何无法修复的 finding 都停止。
2. 审计发现事实修复时，release/hotfix 可写入修复但必须停止；用户手动 commit 后，从 clean 基线重新调用 finish。
3. 零 finding 时，`$mdf finish` 显式组装 `--release-date`、非空 summary 的
   `--semantic-attestation-json`、Bug outcome、major
   Bug 接受和严格 hotfix 输入。hotfix
   JSON 必须有非空 body、至少一条 evidence 和至少一条 release
   note；identity 字段由 Core 注入。验证命令只读取 manifest
   `verification.commands`，并追加到版本根 Change 聚合 evidence。
4. 用户要求 preview 时才加
   `--dry-run`：不运行命令，只返回版本、outcome、移动、受影响文件与命令摘要。正常 apply 直接执行；命令成功后 worktree
必须仍 clean，随后写入并 full
   validate。
5. Core 直接写入；失败现场保留给 Git 历史处理。

release 将 child Change 移到 `changes/<version>/<slug>/`
并生成根 CHANGE；hotfix 要求无 unreleased Change，直接生成根 CHANGE。

## Bug closeout gate

- `fixed`：关闭，写 `fixed_in: <version>`，并提升 sentinel found-in。
- `closed`：关闭并写非 fixed 终态，不写 fixed-in。
- `deferred`：保持 ready，不写 resolution/fixed-in，不归档，仍提升 sentinel
  found-in。
- 每个 `ready` + `found_in: unreleased` Bug 必须分类；critical 只能 fixed；major
  deferred/wont-fix 需要用户接受、理由和 follow-up；duplicate 不进入 outcome。closed
  duplicate 可在 canonical 仍 ready 时存在；release
  closeout 关闭 canonical 后归档整个 group。

## 手动 archive

`$mdf archive`
是独立显式入口，只移动已 closed 对象。若 duplicate 的 canonical 仍 ready，archive 必须拒绝，避免拆开 group。
它直接写入后 full
validate；失败现场保留给 Git 历史处理。closeout 同时归档本次及历史 closed 对象，并检查 duplicate
group 完整性。
