# PR 合并后续办

github-flow 的主线收口目标是 `workflow.trunk`；support hotfix 合回冻结的维护线。
`pm/*` 从 trunk worktree 按 [pm 分支](pr.md#pm-分支) 完成收口。

## 决策树

```text
┌──────────────────────────────┐
│ 1 Check merged               │
└──────────────┬───────────────┘
               │
               ├──── 未 merged ────→ [交接 pr]
               ├──── 身份不符 ─────→ [保留现场，停止]
               │
               ▼ 通过
┌──────────────────────────────┐
│ 2 Finish Gitflow             │
└──────────────┬───────────────┘
               │
               ├──── finish_busy ─────→ [等待持锁调用退出，回 1]
               ├──── 本地集成冲突 ────→ [保留现场，修复并验证后回 2]
               ├──── 其他失败 ────────→ [读日志，保留现场并报告恢复位置]
               │
               ▼ 返回实际结果
┌──────────────────────────────┐
│ 3 Report                     │
└──────────────┬───────────────┘
               │
               ├──── completed 且核验通过 ────→ [返回 close-out 完成]
               ├──── 可修 backmerge ──────────→ [补审补测后回 2]
               └──── 阻塞或证据不符 ──────────→ [保留现场，报告未完成]
```

## 工作流（唯一执行契约）

本页只由 PR mode 的 close-out 调用；pr 已完成实际合并与关联 CI 收尾，不创建 pr Goal。
读取 `references/common.md`；遵守调用方 until 与既有授权。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check merged | 约束 | 锁定 source、模式与原 PR/MR，核实际 merged | 平台与 Git | 2 | 未 merged 交接 pr；身份不符停止 |
| 2 | Finish Gitflow | 脚本 | 从主 worktree 调用 finish-gitflow --source | CLI 结果与实际 Git | 3 | busy 回1；本地冲突修复验证后回2；其他报恢复位置 |
| 3 | Report | 约束 | 核发布、本地集成、backmerge 与清理 | completed、merge_commit、remote_deleted | 完成返回 | 可修 backmerge 修复后回2；否则报告阻塞 |

## 术语与数据结构

### 入口与完成判据

close-out 只执行合并后的剩余工作，不创建或更新 PR/MR、不等待 CI。

- 未 merged 时不能调用 finish-gitflow；返回 pr 尚未完成，不绕过 objectives 顺序。
- merged 但关联 CI 未收尾或缺少证据时先恢复 pr，按 [PR 轮询](pr.md#当前调用内轮询) 核验；通过前不发布或清理。
- 已 merged 后不重做源分支集成、材料、审查或验证；使用平台确认的固定 M。
  - 无账本 adhoc 可通过已知的 source 及平台 PR 核对原 tip。
  - 核规范 Change、平台 source/target/head、双亲 M 与目标远端第一父链，再记录并续办；未 merged 返回 pr。
- source 已删除、owner detached 或外部删除时，仍从同一 Git common dir 的主 worktree 恢复。
- `completed=true` 须同时核对 merge_commit、远端目标、remote_deleted=true 与本地 source 删除。
  owner 存在时核 detached；owner 已外部删除时如实报告，不重建。
- Gitflow 发布交付核 tag 指向 M 和远端 develop 的回合；github-flow 核已发布 tag 的 commit 是 M 的 ancestor。
- 部分成功只补剩余动作，不重复发布；finish_busy 等持锁调用结束，不删除 lock。
- github-flow 的本地 trunk 有未共享 commit 时，`finish-gitflow` 返回 `upstream_diverged` 并保留现场。
  通过显式 [trunk-pr](trunk-pr.md) 或已确认的 sync PR 计划保全这些 commit 并对齐本地 trunk。
  对齐后用原交付 source 续办 close-out，新 PR/MR 可独立等待合并。
- close-out 完成后由 deliver 完成最终核验；其他入口报告后执行公共清理并结束，不再返回 adhoc Select。
  - 更大范围 Goal 的其他工作仍须保留，不因本次交付完成而置 complete。
- CLI 先保留 owner 与 backmerge worktree 供核验；成功收尾后按 [工作区清理](close-out.md#工作区清理) 默认删除，不再单独确认。

### Backmerge 修复

发布后的修复保持固定 M，不重新进入 pr。

- backmerge 的冲突在记录的 `backmerge.worktree` 中解决并提交，保留固定发布提交 M 和 tag。
  - 补审前须 clean；使用独立 `$mdf code-review --against <回合base> --read-only`，覆盖回合与修复。
  - 在该 worktree 用 verify named 执行 lint、build、quick 和原发布所需 suite（release 或 smoke），再按改动补 named suite。
  - fact audit/update 使用 paths 范围，指向受修复影响的事实页；不修改固定发布提交或已发布版本材料。
  - 审查、验证和 fact 证据保存在 checkout 外的运行报告目录；不退勾已发布版本的 objectives，不套用交付 branch 验证。
  - 所需证据齐全并通过后恢复步骤 2；修复后的完整 backmerge HEAD 必须已进入远端 develop，才能完成收口。
  - 修复后由 CLI 直接 push develop；backmerge 不创建 PR/MR，也不进入平台合并轮询。
- 每轮依据新反馈和验证结果推进；仅在用户停止、外部阻塞或无进展且不能安全继续时交接。

### 远端交付分支清理

清理对象为已合并的 PR/MR source，包括 github-flow 的 `pm/*`。gitflow 的常驻 `planning` 不参与 PR/MR 清理。

- 合并核验与所需发布动作完成后，先清理远端 source，再删除本地 source；远端失败时保留本地现场。
  - 普通交付在删除前 detach 已检出的 owner。github-flow 的 `pm/*` 直接清理 source ref，主 worktree 检出 trunk。
- 删除前直接 ls-remote 查询精确 ref，tip 必须等于已确认 PR head；以显式 expected SHA 的 lease 条件删除，不依赖 tracking ref。
  - lease 仅用于删除该 source，不用于改写任何分支历史；并发前进时停止并保留新 tip。
  - 远端已由平台或用户删除时，确认缺失即复用，不重复发删除请求。
- 中断或推送结果不明时，重新查询精确远端 ref。缺失即继续本地清理。SHA 不同，或本地 source 已缺失而同名远端 ref 仍存在时，保留现场。
- 发布重试核对固定 M 与 annotated tag。Gitflow 另核远端 develop 第一父链的双亲回合；已合入回合以远端拓扑为准。
  - 本地和远端 source 均已清理时，只核远端回合证据；证据缺失时停止，保留 backmerge worktree 的后续提交。
- CLI 的 remote_deleted 独立表示已确认远端 source 删除，deleted 仍表示本地 source；全部清理完成后才能 completed=true。

### 发布与回合

本节固定本次发布的实际 merge commit M。release 的 target 为 `workflow.trunk`；
gitflow hotfix 同样合回 trunk，github-flow hotfix 的 target 为冻结的 support 维护线。

步骤 2 的 `finish-gitflow` 固化执行下列发布动作，Agent 只核结果及处理返回的冲突。

| CLI 动作 | 证据 | 失败/缺失去向 |
| --- | --- | --- |
| 核 release/hotfix 平台合并 | 实际 PR target 第一父链中的双亲 M | 停止并保留现场 |
| 核对前置 publish 的 annotated tag、目标 commit 与正文 | 远端 tag 与发布记录一致 | 续办 publish |
| Gitflow 在独立 worktree 将 M no-ff 回合 develop | 远端 develop 包含完整回合 HEAD | 步骤 3 处理 backmerge |
| 清理远端及本地 source，暂留临时目录供核验 | remote_deleted、deleted、owner 状态 | 步骤 3 核对后默认清理临时目录 |

- 不跟随后来前进的 target HEAD；本地 target 只做同名 ff 同步，分歧时保留现场。
- tag push 响应丢失时先核对远端；已存在且符合记录则复用。

以下 backmerge 规则仅适用于 gitflow；github-flow 不回合 develop。

- 本地 develop 的集成遵循下节；远端 backmerge 始终以远端 develop 为 base，不夹带本地独有 commits。
- tag 已发布、回合未完成时返回 published_pending_backmerge。
- backmerge 是直接进入 develop 的特例；使用 no-ff merge 和非 force push，不创建回合 PR/MR。
- 冲突保留在返回的 backmerge.worktree；当前 Agent 解决、补审补测并提交后恢复 close-out，直接 push develop。
- 平台拒绝直接 push develop 时保留 tag、回合 worktree 和 push_error；可修问题自行处理，权限阻塞则报告。
- develop 前进时在回合 worktree 合入远端 develop，解冲突并按影响补审补测；恢复 close-out 后重试直接 push。
- 新 head 必须保留记录的历史和固定 M；改写历史仍停止。
- worktree 创建中断后，已有未占用回合分支与记录的 head（尚无 head 时为 base）精确一致，才复用分支建立工作区。
  分支不符、已被占用或已有 head 的分支丢失时保留现场，不重建或覆盖已记录历史。
- gitflow 的 local 模式按 merge、publish 各自契约推送 trunk 与 tag，develop 只在本地回合。

### 本地 develop 集成

gitflow 的 close-out 要求本地 develop 包含远端交付结果，不要求本地与远端 tip 相同。

- 本地落后时同名 ff；已包含远端时保留本地 commits；双方分叉时将远端 no-ff merge 到本地。
- 不分类、squash 或 push 本地独有 commits，不要求先执行 dev-pr；这些工作的远端交付独立处理。
- 目标 worktree 必须 clean 且无未结束 merge；未被检出时，分叉集成在同级 develop worktree 中执行并保留。
- merge 冲突保留现场，报告 worktree、base 和 remote_head；解决并提交后恢复 close-out，不 reset、rebase 或自动 abort。
- 实际 merge 后按集成影响补审补测；原 PR 的 CI 不代表本地组合已验证，不重开原 PR 或改写固定 M。
  - 调用前记录本地 develop tip；以它为 base 核本轮集成 diff，审查和验证证据保存在 checkout 外。
- 本地集成完成后才清理 source；重入已包含远端时不重复 merge。

### Merge 例外

本节约束 MDF 的 Git 入口；平台可保留正常 push 权限。

| 操作 | PR mode |
| --- | --- |
| gitflow：feature/bugfix/adhoc → develop；release/hotfix → trunk | PR/MR |
| gitflow 的 planning → trunk → develop、trunk → planning | 按 [项目记录](common.md#项目记录) 直接合入，planning 入 trunk 核完整文档历史 |
| github-flow 的 pm/* → trunk | PR/MR，按 [pm 分支](pr.md#pm-分支) 检查路径 |
| gitflow 的 trunk → develop | 允许固定 trunk 历史提交 no-ff 回合 |
| gitflow 的 develop 上纯 MDF/宿主维护 | 允许直接提交和 push |
| gitflow close-out 中 origin/develop → 本地 develop | 允许 no-ff 集成；不 push 本地独有 commits |
| 其他合入受保护的 trunk/develop/support | 拒绝，提示 PR/MR |
| trunk → owner、角色分支 → owner | 沿用现有集成 |

- 完整文档白名单：docs/、changes/、根 *.md、.mdf/ 及以下全部宿主目录。
- 宿主目录：.agents/、.claude/、.codex/、.cursor/、.kiro/、.openclaw/，不限定 skills/mdf。
- develop 默认直接维护仅允许 .mdf/、宿主目录、根 AGENTS.md；项目可按 [dev-pr](dev-pr.md) 覆盖 trivial policy。
- 混入其他路径须 PR/MR；trunk 不增加文件维护例外；禁止 rebase 或跨分支 ff-only。
- gitflow 的 planning 检查独有普通提交、rename/delete 原路径、merge resolution 及最终增量，防止 revert 掩盖代码修改。
- gitflow sync 的 trunk/develop 分叉或无法证明合规的领先增量须走 PR/MR；同名 ff 同步允许。
  - 创建、等待、核验合并及继续同步见 [Sync 的 PR 提交与恢复](sync.md#pr-提交与恢复)。
- push 后审计与项目配置见 [CI 接入](ci-review.md)。
