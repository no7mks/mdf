# PR Close-out

## 决策树

```text
┌──────────────────────────────┐
│ 1 Check                      │
└──────────────┬───────────────┘
               │
               ├──── 不符 ────→ [保留现场，停止]
               │
               ▼ 通过
┌──────────────────────────────┐
│ 2 Prepare                    │
└──────────────┬───────────────┘
               │
               ├──── 缺前置 ────→ [交接主链]
               │
               ▼ 已准备或恢复
┌──────────────────────────────┐
│ 3 Finish                     │
└──────────────┬───────────────┘
               │
               ├──── 失败 ────→ [读日志，保留现场]
               │
               ▼ 返回实际状态
┌──────────────────────────────┐
│ 4 Report                     │
└──────────────┬───────────────┘
               │
               ├──── 等待平台合并 ────────→ [等待 2 分钟，只读查询；合并后回 3]
               ├──── 可修问题 ────────────→ [主链外修复、补审补测后回 3]
               ├──── 关闭但未合并 ────────→ [保留现场，报告未完成]
               ├──── 完成且核验通过 ──────→ [返回调用方]
               └──── 状态不符或缺证据 ────→ [保留现场，停止]
```

## 工作流（唯一执行契约）

本表只由 PR mode 的 close-out 或其恢复调用。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check | 约束 | 核模式、source、origin 与目标现场 | 配置与 Git 状态 | 2 | 保留现场，停止 |
| 2 | Prepare | 约束 | 首次核前置；恢复核返工与操作记录 | 账本、返工备注、平台事实 | 前置齐3；等待留4 | 未完返工交接主链 |
| 3 | Finish | 脚本 | 调用 finish-gitflow 提交或续办 | CLI 状态与平台事实 | 4 | 读日志，保留现场 |
| 4 | Report | 约束 | 核结果；轮询或交回主链修复 | 平台结果、修复与收口证据 | 等待留4；修复后或合并回3；完成返回 | 外部阻塞或未合并报告未完成；缺证据停止 |

## 术语与数据结构

### 模式与入口

本页规定 `closeout.mode: pr` 时的交付与恢复。

```yaml
closeout:
  mode: pr
  provider: github # 或 gitlab
```

- 省略 closeout 时使用 local；init 保留配置，doctor 校验。
- origin fetch/push 地址须一致且唯一，支持 SSH/HTTPS 与自建 host；第一版只支持同仓 PR/MR。
- 项目安装并登录 gh/glab；MDF 不自动配置账号、CI、runner 或 branch protection。
- 初次 close-out 仍按主链完成集成、审查、验证、fact 和材料准备；随后委托本页提交。
- PR mode 的 feature PRP 在源提交中准备 implemented，随 PR 合入 develop 后生效。
- 源分支的候选状态不代表已交付；交付完成看远端目标分支和实际合并结果。
- 已有 Git common dir `mdf/finish/<source>.json` 时先按下方恢复路由续办，不重新执行整套材料准备。
- 每次 CLI 收口持有 Git common dir 的仓库级 OS lock；同源及不同源并发调用返回 finish_busy，不写恢复记录或 Git。
  - lock 只覆盖本次 CLI 操作，不覆盖 Agent 的 2 分钟等待；调用退出或中断时由 OS 释放，不删除 lock 文件。
  - finish_busy 先等待持锁调用结束再续办，不启动第二个写入流程，也不手工删除恢复记录或 lock 文件。

### 恢复路由与返工上下文

deliver、next、人工与 adhoc 续办，以及 close-out 的 Prepare 共用本节，不新增 CLI 或 workflow 状态文件。

1. 先应用当前 until、只读限制与已有有效授权；截止点排除 close-out 时只读报告，不进入返工、push 或轮询。
2. PR 恢复先于 doctor、branch、delivery status 和 adhoc-status；先只读解析 Git common dir 与已锁定 source 的 finish 记录。
   - 先锁定当前完整交付分支、既有上下文或用户指定的 source；尚无目标时才核对唯一未完成 PR 操作记录，不改绑已锁定交付。
   - 核 mode、origin/provider、source、target 与本仓一致；多个候选无唯一依据时澄清，不按时间或目录名猜测。
   - completed 记录仅用于已明确锁定的原交付；不从历史完成记录自动启动任务。
3. owner 已 detached 或 source 已删除时，操作记录仍可指向清理、发布或 backmerge 续办。
   - 使用原 source 与主 worktree；不因 delivery status 不支持 detached 而停止，不重新 start 或重建 owner。
   - 主 worktree 与记录的 Git common dir 必须一致；不存在 PR 记录时才按原入口的普通规则识别。
4. Prepare 先只读查询记录中的原 PR/MR；尚无 PR ID 时按记录的 identity/source/target 查回复用，不能猜测或重复创建。
   - 仅 open 或尚无 PR、仍需候选源提交时，读取原 source worktree 的同一份材料、objectives 与返工备注。
   - 已 merged 或部分发布时，按记录与实际 Git 直接恢复；owner 目录可不存在，必要已交付材料从固定 merge commit 读取。
   - 查无 PR 时，前置齐全才到 Finish 复用或创建；创建响应丢失仍先查平台，不重做首次材料准备。
   - PR/MR 为 open：未完成返工先交回主链；全部完成后才允许更新 PR/MR 或恢复轮询。
   - 已有「PR close-out 返工」备注时，先恢复其中父 intent、原验证请求和未完成子步骤，不按首个退勾项丢弃父流程。
   - 备注尚未清理或所需前置项仍未勾时，不直接调用 finish-gitflow，不用旧通过 report 跳过返工。
   - PR/MR 已 merged 或部分发布时，按实际合并记录续办剩余操作；不修改已交付材料或重新跑交付阶段。
     新的未合入修复与实际 merged head 不符时报告阻塞，不以重新提交改变本次发布。
5. open 且修复已提交、前置齐全时，在原 source worktree 执行 `finish-gitflow --repo <owner>` 更新原 PR/MR。
   - 本地 head 与已确认 head 不同且未完成项已补齐时，先提交候选新 head，不反复处理旧 head 的 review。
   - 只有已准备且无新提交的等待，或 merged/清理/backmerge 恢复，才从主路径带 `--source <原分支>` 续办。
   - owner 缺失且仍需修改或提交新 head 时保留现场并报告，不在主 worktree 代写。
6. 返回 waiting_for_merge 时在当前调用每 120 秒查询新 head 的结果；completed=false 不结束 deliver Goal。
   - next 选中的是父 close-out：内部返工阶段完成后回同一 PR 流程，不递归调用 next，也不创建 deliver。
   - 清理已完成但仍需完成记录或报告时，按记录及实际 Git 核验，不要求已删除的 source 继续存在。

### 生命周期

本节按平台实际状态推进 close-out，不按退出码或 checklist 猜测完成。

| 状态 | 操作 |
| --- | --- |
| 尚无 PR/MR | `finish-gitflow --repo <owner>` 提交候选状态、push 源提交、创建或查回复用 |
| open | CLI 返回 waiting_for_merge；Agent 保留分支与 worktree，在当前调用内每 2 分钟查询平台结果 |
| 未合并时源分支前进 | 所有交付 kind 先完成受影响的主链检查，再非 force push 更新原 PR/MR；不改写历史 |
| closed，未 merged | 返回 closed_without_merge；不清理、不宣称完成 |
| merged | 核 source/target/head、双亲 merge commit、远端第一父链，然后续办 |
| 仅部分后续动作成功 | 核对记录与实际状态，只补剩余步骤 |
| completed | 本地 source 删除；owner 存在时 detached，已外部删除则如实报告；按原清理规则交接 |

- 从主工作区恢复：`finish-gitflow --repo <主路径> --source <原分支>`，支持所有交付 kind。
- 返回 completed=false 是正常等待；调用方须读取 status，不得因退出 0 就结束 deliver Goal。
- PR/MR 由用户或项目 CI 合并；close-out 不批准或合并平台 PR/MR。
- release/hotfix 的源提交在 PR/MR 合并前允许合法前进；合并后固定实际 M，不接受追加提交改变本次发布。
- 首次 push 或创建结果丢失，重入先查平台，禁止重复创建或覆盖记录。
- tag、远端、来源或目标不符时停止；不 reset、不覆盖 tag、不清理他人现场。
- source 清理先核无其他 worktree 占用，再以已确认 head 作 expected SHA 原子删除；并发前进时保留 ref 和分支配置。

步骤 4 核对 `status`、`completed` 与实际结果，按下表等待、续办或返回。

| 结果 | 证据与去向 |
| --- | --- |
| waiting_for_merge | completed=false，PR/MR 为 open；进入下方轮询，平台合并后回步骤 3 |
| published_pending_backmerge | completed=false，tag 已发布；读取 backmerge 冲突或 push_error，修复后直接回合 develop |
| closed_without_merge | completed=false，PR/MR 已关闭但未合并；保留现场，报告未完成，不自动新建 PR/MR |
| completed | completed=true，核对 merge_commit、目标远端引用与本地 source 清理；通过才报告完成 |
| 字段缺失、状态矛盾或核验失败 | 保留现场并停止，报告缺项；不以退出 0、源分支消失或 detached 单独判定完成 |

### 当前调用内轮询

轮询由当前 Agent 执行，不创建 automation、定时任务或后台常驻服务。

- 首次返回等待时报告 PR/MR 链接；此后每 120 秒只读查询该 PR/MR 的 state、head、review/approval 与 CI checks。
  - 使用已登录的 gh/glab 查询记录中的 provider、host、project 和 PR/MR ID；不猜测其他仓库或 PR/MR。
  - 等待拆成不超过 60 秒的可中断调用；期间响应用户输入，累计 120 秒才再次查询平台。
- open 且 CI/review 仍在运行、等待审批或等待自动合并时，继续本轮询，不结束当前 close-out 或 deliver。
  - 没有新结果时不重复汇报；不设固定轮数或总等待超时。
  - 查询本身不重复调用 finish-gitflow，不重复 push，也不调用 approve/merge 或修改 CI policy。
- 确认 merged 后回步骤 3，执行 `finish-gitflow --repo <主路径> --source <原分支>`。
  - CLI 核验实际合并并补剩余收口；release/hotfix 的 backmerge 按下方直接回合规则执行。
  - 只有 completed=true 且步骤 4 核验通过，才能返回交付完成。
- review 要求修改、CI checks 失败或合并冲突时，先读取已有报告与平台详情，按下方修复流程继续推进。
- 权限不足、无法获取必要证据、身份或历史不符等无法安全自行解决的问题，报告具体阻塞并保留现场。
  - head/source/target 变化时核对来源；本轮修复产生的合法前进按修复流程处理，不覆盖他人提交或改写历史。
  - closed 未 merged 按 closed_without_merge 处理；不自动重建 PR/MR。
- 用户要求停止或会话中断时保留恢复记录、分支与 worktree；之后再次 close-out 从该记录续办。

### 反馈修复与重新提交

可修问题交回主链外处理，保持当前任务持续推进；独立 close-out 和 deliver 委托均适用。

1. 核对反馈对应当前 PR/MR 与 head；读取完整 review、CI 日志和失败报告，定位问题，不为查看输出重复运行。
2. 修改前先保存「PR close-out 返工」非 checklist 备注，并按实际影响退勾 objectives 的受影响项及后续项，落盘后再修复。
   - 备注位于本次材料目录的 objectives，记录父 intent 与调用方、原 PR/MR 身份、source/owner/common dir/主路径。
   - 原调用方为 deliver 时保留其有效 until、yolo 与已有授权依据；新调用有显式边界或用户限制时以本次要求为准。
   - 同时记录反馈对应的旧 head、修复前左端点、原验证请求（scope/模块/选题或 suite/完整命令）及返回 PR close-out 的位置。
   - 进度仍只由 checklist 决定；备注只恢复父流程与参数，不另加 gate 或状态协议，不改写人工工作勾选来源。
   - 冲突通过 merge 目标分支解决；不 rebase、不 force push，不覆盖他人现场。
   - CI 暂时故障仅在证据支持时重试；不降低测试、审批或 branch protection 要求。
3. 结束 close-out 内部调用栈，在主链外按影响恢复 lint、增量 code-review、原验证范围及 fact。
   - code-review 与 verify 可相互退回修复，直到问题解决、所需审查和验证通过；同步材料并提交。
   - 独立 close-out 也由当前 Agent 续办上述阶段，不仅报告待办后结束；deliver 返回 Select 按原阶段推进。
4. 全部补审补测与 fact 完成后，复核候选材料、恢复 close-out 候选勾选，在更新 PR/MR 前的材料提交中移除该备注。
   - 清除备注不会提前声明实际完成；中断后按前置全勾、本地 head 与 finish 记录的差异恢复更新，不重做首次材料准备。
   - 恢复 close-out，步骤 3 从原 source worktree 非 force push 合法新提交、复用原 PR/MR，继续每 2 分钟查询新 head。
   - 保留 finish 操作记录；不删除或篡改记录以绕过 CLI 核验。
   - release/hotfix 同样允许在 PR/MR 合并前更新；合并后固定 M，源工作区的新增或未提交改动须在发布前报告。

release/hotfix 的材料即使已位于 `changes/<version>/`，PR/MR 未合并时仍是候选发布材料。

- 在同一版本目录退勾 objectives、更新 code-review、verification-report、fact 与交付总结，不另建 unreleased 副本。
- CLI 的 delivery 与 verify branch 共用候选目录；不得重复 release-closeout、搬回目录或删除 finish 记录。
- 保留原版本和发布范围；按修复同步候选 CHANGE、CHANGELOG 和相关对象，检查链接及声明与实现一致。
- release 首轮审查仍从目标 master 的上一正式发布记录确定基线，不把候选 manifest 的 latest_release 当作已发布版本。
- fact 使用 paths 范围补齐受影响的事实页，避免把尚无正式 tag 的候选版本当作 branch 基线。
- 补审补测与材料提交完成后更新原 PR/MR；合并并发布后，该版本材料冻结。

- backmerge 的冲突在记录的 `backmerge.worktree` 中解决并提交，保留固定发布提交 M 和 tag。
  - 补审使用独立 `$mdf code-review --source-commit <修复后HEAD> --target-commit <回合base>`，覆盖回合与修复。
  - 在该 worktree 用 verify named 执行 lint、build、quick 和原发布所需 suite（release 或 smoke），再按改动补 named suite。
  - fact audit/update 使用 paths 范围，指向受修复影响的事实页；不修改固定发布提交或已发布版本材料。
  - 审查、验证和 fact 证据保存在 checkout 外的运行报告目录；不退勾已发布版本的 objectives，不套用交付 branch 验证。
  - 所需证据齐全并通过后恢复步骤 3；修复后的完整 backmerge HEAD 必须已进入远端 develop，才能完成收口。
  - 修复后由 CLI 直接 push develop；backmerge 不创建 PR/MR，也不进入平台合并轮询。
- 每轮依据新反馈和验证结果推进；仅在用户停止、外部阻塞或无进展且不能安全继续时交接。

### 发布与回合

本节固定本次发布的实际 merge commit M。

1. 确认 release/hotfix 已通过平台 merge commit 合入 master。
2. 在 M 创建 annotated `v<version>`，正文沿用 CHANGELOG 条目，只 push tag。
3. 在独立临时 worktree 将 M no-ff 合回 develop，并验证远端包含 M。
4. 全部完成后清理本地交付 source；临时回合目录保留供检查，不删除主目录。

- 不跟随后来前进的 master HEAD；本地 master/develop 只做同名 ff 同步，分歧时保留现场。
- tag 已发布、回合未完成时返回 published_pending_backmerge。
- backmerge 是直接进入 develop 的特例；使用 no-ff merge 和非 force push，不创建回合 PR/MR。
- 冲突保留在返回的 backmerge.worktree；当前 Agent 解决、补审补测并提交后恢复 close-out，直接 push develop。
- 平台拒绝直接 push develop 时保留 tag、回合 worktree 和 push_error；可修问题自行处理，权限阻塞则报告。
- develop 前进时在回合 worktree 合入远端 develop，解冲突并按影响补审补测；恢复 close-out 后重试直接 push。
- 新 head 必须保留记录的历史和固定 M；改写历史仍停止。
- worktree 创建中断后，已有未占用回合分支与记录的 head（尚无 head 时为 base）精确一致，才复用分支建立工作区。
  分支不符、已被占用或已有 head 的分支丢失时保留现场，不重建或覆盖已记录历史。
- tag push 响应丢失时先核对远端；已存在且符合记录则复用。
- local 模式继续原子 push master + tag，develop 只在本地回合。

### Merge 例外

本节约束 MDF 的 Git 入口；平台可保留正常 push 权限。

| 操作 | PR mode |
| --- | --- |
| feature/bugfix/adhoc → develop；release/hotfix → master | PR/MR |
| planning → develop | 完整文档白名单才允许 no-ff |
| master → develop | 允许固定 master 历史提交 no-ff 回合 |
| develop 上纯 MDF/宿主维护 | 允许直接提交和 push |
| 其他合入 master/develop | 拒绝，提示 PR/MR |
| trunk → owner、角色分支 → owner | 沿用现有集成 |

- 完整文档白名单：docs/、changes/、根 *.md、.mdf/ 及以下全部宿主目录。
- 宿主目录：.agents/、.claude/、.codex/、.cursor/、.kiro/、.openclaw/，不限定 skills/mdf。
- develop 直接维护仅允许 .mdf/、宿主目录、根 AGENTS.md；不判断是否由 upgrade 产生。
- 混入其他路径须 PR/MR；master 不增加文件维护例外；禁止 rebase 或跨分支 ff-only。
- planning 检查独有普通提交、rename/delete 原路径、merge resolution 及最终增量，防止 revert 掩盖代码修改。
- sync 拒绝分叉的 master/develop，以及无法证明合规的本地领先增量；同名 ff 同步允许。
- push 后审计与项目配置见 [CI 接入](ci-review.md)。
