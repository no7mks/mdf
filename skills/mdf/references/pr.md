# PR

feature 的目标为 ODR 时，纳入/收口优先执行 [Late-decision 的纳入路径](late-decision.md#feature--odr-纳入路径)，
不套用本文普通 feature 的材料准备、验收前置或步骤补勾；gitflow 的目标 develop 保持原流程。
github-flow 的 PR 目标是 `workflow.trunk`，不使用 develop。

涉及 master 起点 feature 或 ODR 时，先应用 [Late-decision](late-decision.md)。
ODR 按 release 工作流执行，起点与纳入 checkpoint 按该页；feature 目标从 delivery.json 读取。

<a id="pm-分支"></a>

## pm 分支

github-flow 的 [trunk-pr](trunk-pr.md) 把本地 trunk 的项目记录保全到 `pm/*`。主 worktree 始终检出 trunk。

- 按现有 PR 授权和 Goal 规则，从干净的 trunk worktree 执行
  `mdf.py pr --repo <trunk 路径> --source <pm/分支>`。
- CLI 将确认的源提交通过 refspec 推送到远端 `pm/*`。用同一 source 创建或复用 PR/MR，等待 CI、review 与平台合并。
- `pm/*` 采用本节的 Prepare 和返工流程。记录 PR/MR、source、原 head、反馈与验证结果到会话或 Git common dir 下的本地日志。
  按项目记录的校验和审查推进，跳过普通交付的 `changes/` 候选材料、objectives 备注与 incremental-integration。
- 需要返工、集成 trunk 增量或响应 `squash_required` 时，从主 worktree 执行
  `mdf.py pm rework --repo <主路径> --source <原 pm 分支>`，进入返回的临时 worktree。
  - Proposal 反馈走 [PRP Review](prp-review.md)，由该流程提交评审文件。
  - 集成时用 `merge-no-ff` 合入最新远端 trunk。处理冲突后重新校验记录与完整 PR diff。
  - 整理提交时按 [squash](squash.md) 执行。路径超出白名单时保留现场，按普通交付处理整批改动。
- 临时 worktree 干净且验收通过后，从主 worktree 执行
  `mdf.py pm finish-rework --repo <主路径> --source <原 pm 分支>`。
- CLI 更新原 source ref，删除临时 worktree 和分支。完成后从 trunk 用原 source 续办同一 PR/MR。
- 清理失败时从主 worktree 重试。临时 worktree 有 ignored 文件时，先将要保留的文件移出该目录。
- squash 在验证前中断时保留现场，按原计划使用 `--verify-only` 核对和记录已完成的结果。
- 原 PR 在返工期间已合入时，先将返工提交保全到另一个本地分支。将干净的临时分支恢复到原 source tip，再完成清理与 close-out。
- 若依赖该记录的 start 返回 `pm_pr_pending`，先把包含该记录的提交同步到 start 的目标 ref，再重试。
- CLI 核完整 PR diff、源分支独有提交和合并结果的路径。项目记录使用自身的校验和审查证据。
- 合并及关联 CI 完成后，从 trunk worktree 执行 `finish-gitflow --repo <trunk 路径> --source <pm/分支>`。
  该命令同步本地 trunk，清理远端及本地 source ref，并保留 trunk worktree。

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
               ├──── 缺前置或返工未完 ────────→ [交接主链，完成后回 2]
               ├──── 已确认等待且无新提交 ────→ 4 Report
               ├──── closed 未 merged ────────→ 4 Report
               │
               ▼ 已准备或恢复
┌──────────────────────────────┐
│ 3 Finish                     │
└──────────────┬───────────────┘
               │
               ├──── finish_busy ────→ [等待持锁调用退出，回 2]
               ├──── 其他失败 ───────→ [读日志，保留现场并停止]
               │
               ▼ 返回实际状态
┌──────────────────────────────┐
│ 4 Report                     │
└──────────────┬───────────────┘
               │
               ├──── 等待合并收尾 ────────→ [轮询 PR 与关联 CI；收尾后回 3]
               ├──── 可修问题 ────────────→ [主链外修复、补审补测后回 3]
               ├──── 关闭但未合并 ────────→ [保留现场，报告未完成]
               ├──── 完成且核验通过 ──────→ [返回调用方]
               └──── 状态不符或缺证据 ────→ [保留现场，停止]
```

## 工作流（唯一执行契约）

本表由 `$mdf pr`、deliver、next、adhoc、dev-pr 或 trunk-pr 调用；只适用于 PR mode。
读取 `references/common.md` 与 `references/delivery-contract.md`。

无账本 adhoc 的专用规则适用于本页全部准备、集成、返工与恢复步骤：

- 不读取、创建或勾退 objectives；前置与完成均核实际报告、平台及 Git 证据。
- 「PR 返工」备注写在 adhoc-status 返回目录的 `code-review.md`，保留相同身份、原验证请求与左端点。
  - 审查终稿保留尚未完成的父 PR 备注；补审补测及 fact 完成并提交候选材料时才清除。
  - 备注单列在审查正文之外，可保留恢复所需 SHA；不受审查终稿正文的无 commit hash 约束。
  - 备注仅恢复调用上下文，不作为第二份进度账本；缺少必要参数时停止并报告。
- 无账本 source 按 [Adhoc 检查与事实](adhoc-change.md#检查与事实) 选择验证入口，集成、CI 返工与 hook 后补验也适用。
- Prepare 仅在首次或实际改动使原证据不再适用时执行 adhoc-change 步骤 1–5；已有适用证据逐项复用。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check | 约束 | 核边界、身份、现场并绑定 Goal | 配置与 Git 状态 | 2 | 保留现场，停止 |
| 2 | Prepare | 约束 | 核远端集成、前置与候选材料；恢复返工记录 | 账本、返工备注、平台事实 | 首次/更新/merged3；等待/关闭4 | 未完返工交接主链，完成回2 |
| 3 | Finish | 脚本 | 调用 pr 提交或续办 | CLI 状态与平台事实 | 4 | busy 等待后回2；其他读日志并停止 |
| 4 | Report | 约束 | 核结果；轮询或交回主链修复 | 平台结果、修复与合并证据 | 等待留4；修复后或合并回3；完成返回 | 外部阻塞或未合并报告未完成；缺证据停止 |

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
- 普通交付首次 pr 先完成主链前置，再按下方材料准备条款生成候选材料。
  `pm/*` 使用 [pm 分支](#pm-分支) 的准备流程。
  - 无账本 adhoc 在 Prepare 委托 [无账本 Adhoc 收口](adhoc-change.md) 的步骤 1–5，再返回本页 Finish。
  - 保留真实分支与 worktree，不要求 delivery/objectives；已有损坏账本不能绕过。
- PR mode 的 feature PRP 在源提交中准备 implemented，随 PR 合入已确定目标后生效。
- 源分支的候选状态不代表已交付；交付完成看远端目标分支和实际合并结果。
- PR/MR 未完成时必须保留 source branch 和 owner worktree，不得 detach、删除分支或删除工作区。
  - 等待 review、返工、补验、等待合并和 closed 未 merged 都不进入清理。
  - release/ODR/hotfix 须先完成 publish，close-out 再核对固定发布点与适用的 backmerge，之后才可清理远端及本地 source；CLI 始终保留 owner worktree。
  - worktree 删除只在实际收口及最终核验完成后，按 [工作区清理](close-out.md#工作区清理) 默认删除临时 owner 和 backmerge；不能凭 checklist 全勾或 PR 已创建提前删除。
- 每次 CLI 收口持有 Git common dir 的仓库级 OS lock；同源及不同源并发调用返回 finish_busy，保留 Git 现场。
  - lock 只覆盖本次收口操作；调用退出或中断时由 OS 释放，不删除 lock 文件。
  - finish_busy 先等待持锁调用结束再续办，不启动第二个写入流程。

### Goal 与持续推进

在入口确认允许进入 pr、锁定交付身份后，先执行本节，再进行远端集成、材料准备或恢复。
独立 pr、deliver 委托、next 恢复及 adhoc 共用本节；local 模式不创建 pr Goal。

| 已有 Goal | 处理 |
| --- | --- |
| 没有未完成 Goal | 创建本次 pr Goal |
| 阶段 Goal 的完成判据已全部满足 | 先核验证据并置 complete，再创建本次 Goal |
| 未完成 Goal 已覆盖本次 pr | 复用，不重建；同范围续办沿用原 Goal |
| 未完成 Goal 范围更大 | 复用父 Goal，将本次 pr 及完成判据加入其剩余工作，保留原目标与其他未完成项 |
| 无关且未完成 Goal | 保留原 Goal，报告范围冲突；不自动 cancel、覆盖或假称完成 |

- 先读宿主实际 Goal 状态与目标；不能仅因进入 pr 就认定旧阶段已完成。
- 宿主支持更新目标或子项时，将新增收口要求写入父 Goal；仅支持状态更新时，在当前上下文记录父 Goal 与收口要求的关联。
  - 后者不得声称已修改宿主 objective；恢复时从原 Goal、交付记录与返工备注重新核对剩余工作。
  - 不为追加子工作而 complete 或重建尚未完成的父 Goal，不取消既有 Goal。
- objective 包含交付身份、source/target、已知 PR/MR、有效边界与完成判据；尚未创建 PR/MR 时不伪造 ID。
  - 持续等待当前 head 的 CI/review，解决可修反馈，补审补测并更新原 PR/MR。
  - 平台实际 merged，且 source/target/head、双亲 merge commit 与远端第一父链核验通过。
  - `pr` CLI 返回 `status=merged`、`completed=true` 是必要但不充分的证据；还须按下方轮询规则核关联 CI 收尾。
- 轮询、主链外返工与重新提交始终沿用同一个 Goal；子阶段完成不结束父流程。
  - CI 全绿或 review 通过不能完成 Goal；实际 merged 且 CLI 合并核验与关联 CI 收尾均通过后结束 pr Goal。
  - 正常 pending 保持 active；可修失败继续推进，不因一次失败结束任务。
- 仅本次创建或同范围复用的 Goal，可在 pr 合并核验与关联 CI 收尾完成后置 complete。
  - 复用更大范围 Goal 时只记录本次收口完成并返回父流程；父 Goal 仍有剩余工作时不得置 complete。
- 用户停止、预算限制、会话中断或无法自行解决的阻塞按宿主规则处理；保留恢复证据，不标完成。
- 宿主不提供 Goal 时仍按本页轮询与恢复规则推进，并如实说明缺少跨 turn 自动续办保障。
  Goal 不替代平台合并授权，也不越过 deliver 的 until、只读限制或用户暂停。

- pr Goal 完成后交回调用方续办 close-out；它有独立完成判据，不属于 pr Goal。
  独立 pr、deliver / adhoc 按该步骤继续 close-out；显式 until、用户停止或暂停仍须遵守。
- 普通 next 保持单步语义：本次若选择 pr，完成后报告 close-out 为下一步，不升级为 deliver。

### 提交前远端集成

- 首次提交及更新 PR 前，核对 catch-up、consolidate 和适用的 publish 已完成。
- fetch 目标 target，把 target 合回当前工作分支。github-flow 已发布 release 继续使用同一工作分支。
- 有 change 时，在 pr 内部执行 [incremental-integration](incremental-integration.md)。
- incr-cr → verify smart → incr-fa → 适用的 incr-consolidate 全部通过后再提交 PR。
- 本轮 base 为合回前已验收状态；修复与冲突解决累计在本轮，target 再次前进时循环处理。
- 保留已通过的基线 CR、verify、FA 与 consolidate 状态；本轮结果追加，验证写独立报告。
- PR/MR 必须保留源提交并采用 no-ff merge，禁止 rebase 与 force push。
- 项目记录 pm 分支继续按本页 pm 规则处理；无账本 adhoc 按已有材料完成对应增量验收。

### 恢复路由与返工上下文

恢复先核调用边界，再用 chat 中的交付身份查询 Git 和平台。

- PR 恢复优先于 doctor、branch、delivery status 和 adhoc-status；先应用当前 until。
  未 merged 选 pr；已 merged 且 CI 收尾通过后，Gitflow 发布交付先选 publish，其余选 close-out；显式 until pr 不进入这两个阶段。
  merged 但关联 CI 未收尾或缺少证据时先恢复 pr，按下方轮询规则查回关联运行。
- source 来自 chat、当前完整分支或用户指定。身份不足或多个候选时，向用户确认 source 和 PR/MR ID。
- 核仓库、origin/provider、source、target 和 head；身份不符保留现场。
- 已知原 PR/MR ID 时传 `--pull <id>`；创建响应丢失时按 source 查询平台并复用唯一结果。
- open 且有未完成返工时先恢复「PR 返工」非 checklist 备注。
  保留父 intent、原验证请求、修复前左端点、未完成子步骤，全部完成后才允许更新 PR/MR 或恢复轮询。
- 无新提交且已确认 open 时只轮询；有新 head 时先完成 Prepare 的最终候选复核。
  `pm/*` 按[本页修订流程](#pm-分支)清理临时 worktree 后，从 trunk 续办原 PR。
  普通交付从原 source worktree 调用 CLI；owner 缺失且仍需修改时报告阻塞。
  续办不重新 start。
- merged 时调用 `mdf.py pr --repo <主路径> --source <原分支>` 核验合并，关联 CI 收尾通过后结束 pr；Gitflow 发布交付进入 publish，其余进入 close-out。
  已进入发布或清理的恢复直接执行 [合并后续办](pr-close-out.md)，不重开 pr Goal。
- 清理前置已全部完成、detach 或删除 source 后中断时，从主 worktree 续办 close-out。
  此恢复容错不授权任何流程提前删除 source 或 owner；发布未完而 source 缺失须核实际证据。
- `pr` 在 push 前执行 squash 必要检查；squash_required 时按返回范围整理后重试，不 force push。
  squash 后 HEAD 变化，须返回 Prepare 重做最终候选复核，不能直接重试 push。
- `finish_busy` 时等待持锁调用退出；等待持锁进程退出后重试。

### 生命周期

本节核对平台实际状态、合并结果和关联 CI，判定 pr 是否完成。

| 状态 | 操作 |
| --- | --- |
| 尚无 PR/MR | 前置与材料齐全后调用 `mdf.py pr --repo <owner>`，push 并创建或查回复用 |
| open | status=waiting_for_merge、completed=false；保持 Goal active，持续轮询 |
| source 前进 | 完成补审补测与 fact，非 force push 更新原 PR/MR |
| closed，未 merged | status=closed_without_merge、completed=false；保留现场，不自动新建 |
| merged | 核身份、head、双亲 merge commit 与远端第一父链；CLI 返回 status=merged、completed=true 后仍须核关联 CI 收尾 |

- PR/MR 由用户或项目 CI 合并；pr 不批准或合并平台 PR/MR，不修改 CI policy。
- pr 完成后，tag 由 publish 负责，适用的 backmerge、source 清理和 detach 由 close-out 负责。
- 未 merged 必须保留 source branch 和 owner worktree；等待 review、返工、补验和 closed 均不清理。
- source/target/head 或实际 M 不符时保留现场；不 reset、覆盖 tag 或改写已合入结果。

### 当前调用内轮询

当前 Agent 报告 PR/MR 链接后，运行以下 CLI：

```bash
python3 "$MDF_ROOT/scripts/mdf.py" pr-watch --repo "$REPO_ROOT" --source "$SOURCE" --pull "$PULL_ID" --head "$SOURCE_HEAD"
```

- CLI 用已登录的 gh/glab 查询 origin 上的 PR/MR，每轮核对 ID、source、target 和已确认的 head。
- 当前 Agent 保持该调用运行，使用可中断的短等待读取结果并响应用户输入。
- 关联 CI 覆盖当前 head、merge commit、平台关联的运行及非 required checks，也包括发起 PR/MR 和执行 merge 的 workflow run / pipeline。
  - GitHub 结合 PR 事件和 commit check 关联 Actions run；GitLab 查询 MR pipeline 及下游 pipeline。
  - 从调用上下文或平台证据确认发起 PR/MR 和执行 merge 的运行 ID，通过可重复的 `--origin-run <id>` 补充平台未关联的运行。
  - 这些运行可能使用另一个 SHA。恢复或 push 后继续传入已确认的 ID；发现补充证据时用完整 ID 列表重新轮询。
  - GitHub Actions bot 合并时，至少要有一项关联 run 的活动时间覆盖合并时刻。项目上下文可用来确认具体执行 merge 的 run。
  - 保留运行的 run ID、attempt、URL 与 head；返回状态附带关联检查证据。
- 每轮核完整 run / pipeline 的状态、结论和全部 job 与 step，step 使用平台提供的结构化数据。
  - 查询须遍历分页；发现新 job、关联运行或 rerun attempt 时更新范围，不能复用旧 attempt 的成功结论。
  - 已关联运行从列表消失时，按已记录的 ID 回查。open 阶段确认的关联在同一轮询中延续到 merged。
  - PR 已 merged 但关联运行未结束时，保持 Goal active；queued、in_progress、waiting 等状态继续等待。
- PR/MR 已合并且 CI 通过后，fetch 目标远端 ref，核对双亲 merge commit 和目标远端第一父链，随即复查平台状态。
  - PR/MR 身份、merge commit 及检查证据一致时立即返回 `merged`。新增 run、attempt、状态变化或已关联运行缺失时继续轮询。
  - open、CI pending、查询失败或证据缺失时等待 120 秒重试；等待无固定轮数或总超时。
- CLI 返回 `merged` 后回步骤 3，执行 `pr --repo <主路径> --source <原分支>` 核验 Git 合并结果。
  - CLI 仅核验实际合并；`status=merged` 且 `completed=true` 后，关联运行也全部结束且结论通过才返回 pr 完成。
  - 仅在项目 policy 允许 skipped / neutral 时传 `--allow-skipped`；cancelled、timed_out、action_required 不算通过。
  - 调用方继续选择 close-out；不得将 pr 完成报告成整个交付完成。
- 关联运行失败时读取失败 job / step 的日志与报告，按证据修复或处理阻塞；不能因 PR 已 merged 忽略失败。
  - 合并后的失败不得向已合入的 source 追加提交、重开原 PR 或改写固定 M；需要代码修改时按调用边界另行交付。
  - 仅有证据支持暂时故障且已有授权时重试；否则报告运行链接、失败 job 与恢复位置，保留未完成状态。
- 查询失败和平台关联证据缺失写入 `polls.jsonl`。持续缺少权限或必要证据时报告阻塞，保留 Goal 和现场。
  - 平台各查询均完整返回且已确认的关联范围为空时，按无 CI 处理；完成前同样立即复查。
- CLI 返回 `changes_requested`、`ci_failed` 或 `merge_conflict` 时，先读取已有报告与平台详情，按下方修复流程继续推进。
  - 一份 review 的返工处理完成后，在现有交接上下文保留 `change_requests` 返回的 ID。再次轮询时每个已处理 ID 各传一次 `--handled-review <id>`。
  - CLI 继续等待平台复审。新 ID 仍触发返工；`review_identity_unknown` 时先核平台反馈，避免把未识别的请求当成已处理。
- 权限不足、无法获取必要证据、身份或历史不符等无法安全自行解决的问题，报告具体阻塞并保留现场。
  - head/source/target 变化时核对来源；本轮修复产生的合法前进按修复流程处理，不覆盖他人提交或改写历史。
  - closed 未 merged 按 closed_without_merge 处理；不自动重建 PR/MR。
- 用户要求停止或会话中断时保留分支、worktree 和已有证据；续办时重新查询平台。

### 反馈修复与重新提交

- 可修 review/CI 反馈、目标前进与冲突都在当前 pr 调用内持续处理。
- 固定本轮已验收 HEAD，修复后执行 incremental-integration；验收前保持工作分支与现场。
- Gitflow 和 github-flow feature/bugfix 完成 incr-consolidate，同步 Change、对象状态与交付材料。
- github-flow 已发布交付追加集成记录，final tag 始终保持发布时的 commit 和正文。
- 已完成的 CR、verify、FA 和 consolidate 保持完成，新增改动在本轮增量验收内部闭环。
- 目标再次前进时继续 target → 工作分支、incremental-integration、提交更新的循环。
- 在更新 PR/MR 前的材料提交中移除已完成的返工备注，保留实际验收证据。
- 更新后恢复原 PR/MR 的轮询，沿用当前 source；已 merged 后转入下一阶段。

### 候选材料准备

- 交付文档、对象状态、版本聚合与归档统一由 [consolidate](consolidate.md) 完成。
- PR Prepare 核对其结果，候选材料需要更新时在 incremental-integration 中执行 incr-consolidate。
- 无账本 adhoc 沿用 [无账本交付材料](adhoc-change.md) 的对应规则。
- 每次 push 前执行 [PR 最终候选复核](fact-audit-delivery.md#pr-最终候选复核)。
  当前 head 的纯轮询和已 merged 核验复用已完成证据。

### 完成与交接

交付清单止于 consolidate，github-flow 发布交付还包含 publish；其后阶段按实际 Git 结果续办。

- 实际 merged、合并核验与关联 CI 收尾均通过后，pr 完成后，Gitflow 发布交付进入 publish，其余进入 close-out。
- close-out 按 [合并后续办](pr-close-out.md) 核发布、backmerge 与清理结果。

### 调用边界与提交裁定

步骤 1、每次内部委托及步骤 3 提交前，先核当前调用的边界与有效授权。

- deliver 委托先核 until，再按 deliver-policy 核 pr 入口确认（yolo 跳过）；沿用其 confidence 策略。
  被截止的 pr 不绑定新 Goal、不准备材料、不 push 或轮询。
- 创建或更新 PR/MR 前按 deliver-policy 裁定源提交与 push；低 confidence 返回 deliver 步骤 6。
  yolo 不受 confidence 限制；独立 pr 沿用调用授权，不引入 deliver 的评分。
- 每次可能 push 新 head 的步骤 3 调用前，必须完成 Prepare 的最终候选复核；恢复或返工直达步骤 3 也不豁免。
  当前 head 的纯轮询、已 merged 核验与合并后 close-out 不适用。
- squash、bug close、code-review、verify 与 fact 的内部返工也先核 until；被截断返回外层，不绕过边界。
- 仅 pr 的实际合并核验与关联 CI 收尾均完成才结束其同范围 Goal；随后按原调用边界交接 close-out。
