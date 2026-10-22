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
| 2 | Prepare | 约束 | 首次完成主链前置；恢复核对操作记录 | 材料或恢复记录 | 3 | 交接主链 |
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
- 已有 Git common dir `mdf/finish/<source>.json` 时先续办本页，不重新执行整套材料准备。

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
| completed | 本地 source 删除、owner detached；保留工作区，按原清理规则交接 |

- 从主工作区恢复：`finish-gitflow --repo <主路径> --source <原分支>`，支持所有交付 kind。
- 返回 completed=false 是正常等待；调用方须读取 status，不得因退出 0 就结束 deliver Goal。
- PR/MR 由用户或项目 CI 合并；close-out 不批准或合并平台 PR/MR。
- release/hotfix 的源提交在 PR/MR 合并前允许合法前进；合并后固定实际 M，不接受追加提交改变本次发布。
- 首次 push 或创建结果丢失，重入先查平台，禁止重复创建或覆盖记录。
- tag、远端、来源或目标不符时停止；不 reset、不覆盖 tag、不清理他人现场。

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
2. 在原 source worktree 修复；记录修复前 HEAD 作为增量审查左端点，按实际影响退勾 objectives。
   - 冲突通过 merge 目标分支解决；不 rebase、不 force push，不覆盖他人现场。
   - CI 暂时故障仅在证据支持时重试；不降低测试、审批或 branch protection 要求。
3. 结束 close-out 内部调用栈，在主链外按影响恢复 lint、增量 code-review、原验证范围及 fact。
   - code-review 与 verify 可相互退回修复，直到问题解决、所需审查和验证通过；同步材料并提交。
   - 独立 close-out 也由当前 Agent 续办上述阶段，不仅报告待办后结束；deliver 返回 Select 按原阶段推进。
4. 恢复 close-out，步骤 3 非 force push 合法新提交、复用原 PR/MR；新 head 等待新的 CI/review 后继续每 2 分钟查询。
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
