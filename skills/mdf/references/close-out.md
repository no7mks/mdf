# Close-out

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check entry                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Integrate and review           │
└────────────────┬─────────────────┘
                 │
                 ├──── dry-run 建议且用户确认执行 ────→ [委托 squash 后继续本步]
                 ├──── 已收口且证据有效 ──────────────→ 4 Recheck
                 ├──── 集成冲突无法解决 ──────────────→ [停止并询问]
                 ├──── 内部审查失败 ──────────────────→ [停止]
                 ├──── 状态不一致 ────────────────────→ [停止]
                 │
                 ▼ 待收口或 feature/bugfix
┌──────────────────────────────────┐
│ 3 Prepare materials              │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留现场，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 4 Recheck                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过，已收口或 feature/bugfix ────→ 9 Hand off
                 ├──── 未通过 ───────────────────────────→ [停止并交接]
                 │
                 ▼ 通过，待收口的 release/hotfix
┌──────────────────────────────────┐
│ 5 Prepare closeout               │
└────────────────┬─────────────────┘
                 │
                 ├──── release 输入完整 ────→ 7 Prepare closures
                 ├──── 输入缺失 ────────────→ [停止]
                 │
                 ▼ hotfix 输入完整
┌──────────────────────────────────┐
│ 6 Check hotfix                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 7 Prepare closures               │
└────────────────┬─────────────────┘
                 │
                 ├──── bug close 改了实现 ────→ 4 Recheck
                 ├──── bug close 未通过 ──────→ [停止]
                 ├──── 失败/缺失 ─────────────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 8 Close release                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败 ────→ [保留现场并停止]
                 │
                 ▼ 收口成功
┌──────────────────────────────────┐
│ 9 Hand off                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 主线前进，feature/bugfix ───────→ 2 Integrate and review
                 ├──── 主线前进，release/hotfix ───────→ [报告并停止]
                 ├──── 交付条件未通过 ─────────────────→ [报告并停止]
                 ├──── auto-pilot 非 yolo 且须确认 ────→ [返回 deliver 步骤 6]
                 │
                 ▼ 通过且无关口（含独立 finish / 默认 deliver / yolo）
┌──────────────────────────────────┐
│ 10 Finish Gitflow                │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ──────────────────→ [核验、报告并询问工作区清理]
                 ├──── 失败且用户决定继续 ────→ 10 Finish Gitflow
                 ├──── 失败且未决 ────────────→ 10 Finish Gitflow
                 └──── 失败且用户停止 ────────→ [报告现场并停止]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

- 读取 `references/common.md`、`references/repository-contract.md`：
  - 另读 `references/object-contract.md` 与 `references/delivery-contract.md`。
- 入口前置：主链须已完成 verify branch（有效 `verify.branch.json`）与 fact audit；
  本 intent 不再内嵌二者。
- 步骤 2 需要审查时读取并内部执行 `references/code-review.md`。
- 步骤 2 可选 squash：先内部执行 `references/squash.md` 的 dry-run，确认执行后再
  内部执行完整 `references/squash.md`。
- 步骤 7 有待收入的 `fixed` Bug 时读取并内部执行 `references/bug-close.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check entry | 脚本 | 确认实际收口授权；运行 doctor 与 branch | ready、Gitflow 分支 | 2 | 停止 |
| 2 | Integrate and review | 约束 | 委托 squash；集成；审查 | 集成、审查 | 已收口 4；否则 3 | 冲突询问；否则停止 |
| 3 | Prepare materials | 约束 | 核对已有 full/fact；整理材料 | full 证据、fact、Change | 4 | 保留现场，停止 |
| 4 | Recheck | 约束 | 核 report/勾选；失效交接 | 有效证据 | 已收口或 feature/bugfix→9；待收口→5 | 未过则停止并交接 |
| 5 | Prepare closeout | 约束 | 只读核对 child Change、日期及热修复输入 | 完整收口输入 | release 7；hotfix 6 | 停止 |
| 6 | Check hotfix | 约束 | 校验 hotfix 结果 JSON 的字段与非空要求 | 有效 JSON | 7 | 停止 |
| 7 | Prepare closures | 约束 | bug close 关闭 fixed；准备 closures | 覆盖、接受记录 | 改了实现→4；否则 8 | 停止 |
| 8 | Close release | 脚本 | 确认 clean，实际运行 release-closeout | 退出 0、产物与 diff | 9 | 保留现场，停止 |
| 9 | Hand off | 约束 | 提交并复核 | clean | 无关口 10；AP 非 yolo→deliver 6 | 主线前进时 feature/bugfix 回 2；其余停 |
| 10 | Finish Gitflow | 脚本 | 运行 finish-gitflow 并按 kind 核 Git 结果 | Git 结果 | 结束 | 继续或未决则 10；停止则停 |

## 术语与数据结构

### 交付范围与审阅

**入口** <a id="s1"></a>

- 本 intent 执行实际收口，不提供预览模式。
  - 用户明确要求仅预览或只读时，说明此入口不支持并停止。
  - ❌ 不得将只读请求视为写入、验证命令或 Gitflow 操作的授权。
- 解析目标 Git 根为 `REPO_ROOT`，运行 `doctor` 与 `branch`。
- 验收：
  - manifest `ready`、非 detached。
  - Gitflow 分支为 `feature/*`、`bugfix/*`、`release/<semver>` 或 `hotfix/<semver>`。
  - 实际收口授权；只读请求在本步骤停止。

**范围** <a id="s2"></a>

先识别本次相关未提交改动，按公共规则复核并提交后确定交付范围；范围不明时先澄清。

- 写入前按 code-review 记录固定交付范围：
  - feature/bugfix/hotfix 为分支 start_commit 到 HEAD。
  - release 为上一正式发布版本的固定 commit 到 HEAD，另核对全部 child Change。
- 检查代码、配置、schema、测试、当前事实、Proposal、Bug、Change，识别应更新文档。
- release/hotfix 同时检查 `changes/<version>/CHANGE.md` 与 manifest：
  - 版本根不存在，且 latest_release 为 null 或按稳定 SemVer 比较小于目标版本时，判为待收口。
  - 版本根已跟踪、已提交，且 version、change_kind、source_branch 与当前分支完全一致、
    latest_release 等于目标版本时：
    - 运行文档 full validation（不跑 `$mdf verify`），并按步骤 4 已收口规则
      核对版本根证据仍覆盖当前交付结果；通过才判为已收口。
  - 版本根提交后有未纳入收口的交付改动、记录缺损或状态不一致时停止，不覆盖版本目录。

待收口或 feature/bugfix 在当前交付分支先集成目标主线，再核对审查证据：

- **可选 squash**（第一次把目标主线合入交付分支之前；嵌在本步、不改编号）：
  - 先内部执行 `references/squash.md` 的 dry-run（由 squash 定地板/切段/message）。
  - dry-run 不可压或失败 → 跳过。
  - 用 `delivery-contract.md`「是否建议」启发式（地板取 dry-run 计划）决定是否向
    用户展示该建议；未达信号也可展示。
  - 用户确认执行后，再内部执行完整 `references/squash.md`（可复用同会话计划）。
  - 拒绝展示、拒绝执行或未确认 → 跳过。
  - ❌ `--auto-pilot` / `--yolo` 不得擅自 squash；禁止 rebase / `merge --squash`。
  - 执行委托完成后须 clean，且树与 squash 前 tip 一致。
- 目标主线：
  - feature/bugfix 使用本地 develop，不 fetch、不 push。
  - release/hotfix 使用 master，先 fetch origin 并核对本地 master/develop 与远端一致，不自动覆盖分歧。
- 集成：
  - 确认 clean，记录目标主线的完整 commit 与当前 HEAD。
  - 若它尚不是当前 HEAD 的祖先，运行：
    - `python3 "$MDF_ROOT/scripts/mdf.py" merge-no-ff --repo "$REPO_ROOT" --commit <目标commit>`
  - ❌ 禁止 rebase，不在主线上解决交付冲突。
- 冲突：
  - 冲突时 CLI 保留 MERGE_HEAD；
    Agent 按已确认目标、设计及两侧改动自动尝试 resolve，逐项核对后提交 merge。
  - ❌ 不得整侧覆盖或削弱测试来消除冲突。
  - 语义不明、需变更目标或无法解决时才停止询问，报告冲突与已尝试的修复。
- 跳过判定：本次集成产生新提交后，用 `git diff --name-only <集成前HEAD> HEAD` 判定增量。
  - 全部路径都在 `docs/` 下，且与本交付文档无交集时跳过：
    - 不启动 code-review；沿用已有 code-review 终稿与主链 `verify.branch.json`
      （须存在且 `all_passed: true`；否则按下方停止）。
    - 在 `code-review.md` 追加跳过说明（merge commit、路径清单；仍不得写入 commit
      hash）。
  - 本交付文档 = 当前对象文件，以及本分支自 start_commit 到集成前 HEAD 改过的 `docs/` 路径。
    - 当前对象文件：feature 的 PRP、bugfix/hotfix 的 Bug、release 的全部 child 对象。
  - 路径不明则不可跳过。
- 不可跳过时：
  - 若集成后无有效 `verify.branch.json`（缺失，或未声称 `all_passed:true`），
    或集成引入了实现/测试改动：
    - **停止并交接**：须在本 intent **之外**由主链重跑 `$mdf verify` branch 并自勾后再
      续办 close-out；❌ 本 intent 不委托、不执行 verify（含 full / smart / run）。
    - 不做 commit 对齐审判。
  - 有有效 full 且无实现/测试增量、仅需审查时，进入 code-review 增量轮：
    - feature：objectives 的 converge 项须已勾；未勾停止。
    - 上轮多人结论必须已由 owner 汇总进终稿的已采纳/未解决清单，
      不得把上轮多份原文交给本轮唯一 reviewer 去合并。
    - 以集成后的 HEAD 执行增量新一轮 code-review：
      左端点为集成前 HEAD（当场记录），重新固定 review_head。
    - 本轮应派人数为 1（不改冻结 roster），覆盖增量并复核上轮问题，
      完成裁定、修复与按需 smart；再洗成无 commit 终稿。
    - 不复用集成前终稿充当增量差，也不将集成当作旧审查的修复续办。
    - 无有效上轮（无终稿或清单残缺）时按首轮从交付起点审到集成后 HEAD，不得跳过，
      人数仍为 roster.reviewers。
- 主线已包含且审查报告已交时无需重复合并或审查。
  - report 缺失时内部执行 code-review，通过后继续本次 close-out。
  - feature：converge 须已在 objectives 勾选；审查看 `code-review.md`（report）。
- 📌 四种分支均须有完整的各轮应派份数独立审查、主 Agent 裁定、修复复核与 smart 记录。
- 已收口 release/hotfix 只核对已有集成与审查报告。
  - 若需要新集成或实现修改，停止报告收口状态不一致，不得覆盖版本目录或改写已开始发布的源提交。
- 验收：精确实现与文档路径、目标主线已包含、集成后的审查与验证报告、版本状态。
- 通过条件：待收口或 feature/bugfix 到 3，已收口到 4。
- 异常与交接：报告缺项或不一致并停止。这是交付前检查；fact audit 已在主链完成。

**材料** <a id="s3"></a>

- 确认主链 report **已交且声称通过**：
  - 存在 `verify.branch.json` 且 `all_passed: true`（只认声称通过，不做 commit 对齐）。
  - 存在 `fact-audit.md`（或等价确认记录）表明已确认通过。
  - objectives 中 verify branch / fact audit 已勾。
  - 缺失则停止并报告账本/产物不一致；由主链在本 intent 外补 `$mdf verify` /
    `$mdf fact audit`，❌ 本 intent 不委托补跑。
- ❌ 本 intent 不内嵌、不委托 verify branch / smart / run，也不内嵌 fact update /
  fact audit；不做 commit 对齐审判。bug close（步骤 7）不算 verify 族，可留。
- 调用方提交材料与证据。
- 按分支准备材料：
  - feature：在 `changes/unreleased/<slug>/` 补齐唯一 PRP 对应的 CHANGE.md。
    - 与 objectives、design、可选 gates/ 同级；材料不搬迁。
    - CHANGE.md 整理完成后提交，再进入阶段校验。
  - bugfix：按对象契约准备当前分支的 `changes/unreleased/<slug>/CHANGE.md`，
    slug 为 Bug ID 的 kebab-case（小写）。
    - start 已写入的 objectives checklist 保留；不要求 design、唯一 PRP。
      记录实际 Bug outcomes 和证据。
  - `source_branch: develop` 的直合 Change 不属于本 finish；目录自选 slug，
    只作为后续 release 的 child 聚合。
  - release：核对已有 child Change 与 `objectives.md`；材料聚合与版本目录写入留给步骤 8。
  - hotfix：不创建 child Change，实际结果 JSON 留给步骤 6 校验。
- 对象状态：
  - feature/bugfix 不建版本目录。
  - feature 在成功合入 develop 的 merge commit 中转换为 implemented。
    bugfix 的对象状态按既有契约处理。
  - release/hotfix 按后续收口步骤管理版本与对象。
- 验收：事实一致性、所需 report 已交、规范 Change 和链接检查。
- 异常与交接：保留现场；缺少前置阶段时报告，不自动执行被跳过的主线 intent。

**审阅** <a id="s4"></a>

- 四种 kind：核对 report 交没交（存在且声称通过），**不**复验对不对。
  - `code-review.md` 终稿存在、声称通过，且无 commit hash。
  - `verify.branch.json` 存在且 `all_passed: true`（已收口 release/hotfix 看版本目录归档件）。
  - fact 确认记录存在。
  - objectives：converge → code-review → verify branch → fact audit 均已勾（feature 另须
    design/开发依赖项已勾）。
- ❌ 不运行 `delivery check --stage finish`；不做 verify 报告的 commit 对齐审判。
- 已收口 release/hotfix：核对 `changes/<semver>/` 归档 report；
  - 用 `git log -1 --format=%H -- …/code-review.md` 定位终稿落盘提交。
  - 自该提交到 HEAD 只允许以下路径：
    `changes/`、`CHANGELOG.md`、`.mdf/manifest.yaml` 与 `docs/`。
    否则按收口状态不一致停止。
- report 缺失或未声称通过时：停止并交接；由主链补跑对应 intent（verify /
  fact / code-review），不在本 intent 内嵌、不做过期审判。
- 集成后需补审时从 `code-review.md` 步骤 1 执行（有有效终稿则增量，否则首轮）。
- 不回退本流程步骤编号。
- 其他失败走本步骤的失败去向。
- ❌ 不在本步重新委托 fact audit / fact update；仅确认主链前置已满足。
- 验收：各分支 `code-review.md` 结论可用；objectives 前置已勾；主链 fact 确认已提交。
- 通过条件：已收口 release/hotfix 或 feature/bugfix 到 9；待收口 release/hotfix 到 5。
  - 本次是否写入不改变该分流；相关材料先按公共规则提交，再继续收口。

### 版本收口输入与执行

**输入** <a id="s5"></a>

- 只读准备收口输入：release 读全部 unreleased child Change（移动留给步骤 8）；
  hotfix 无 child Change 且提供实际结果 JSON；两者均提供规范 `--release-date`。
- 验收：完整版本收口输入。通过：release→7，hotfix→6。异常：停止。
- Core 记录确定性审计；语义审阅用本次已确认 audit。

**热修复** <a id="s6"></a>

- 校验 hotfix `--hotfix-change-json`：必填 body、release_notes、evidence；
  可选 proposals、fixed、closed、deferred、adrs、breaking。
  - body 非空；三类 evidence 合计至少一条；release notes 至少一项非空。
- 验收：有效 JSON。异常：未知字段、空串或缺字段则停。
- Core 注入 change_kind 与 source_branch。

**对象** <a id="s7"></a>

- 待收入 `fixed` outcome：`status: fixed` 且 `found_in: unreleased`，以及
  child Change `fixed:` 中仍为 `fixed` 的 ID。
- 待收入 fixed 先委托 bug close；已 closed 且 fixed_in 等于本版的 Bug 纳入 fixed outcome。
  close-out 只核对版本、聚合和归档，不重复关闭。
- 委托 bug close：
  - 清单非空时内部执行 `references/bug-close.md`，传入这些 ID 与 `--fixed-in <当前发布版本>`；空则跳过。
  - 未通过则本步失败，不准备 closures，不关闭对象。
  - 「实现已变更」：提交后回步骤 4（不 closures、不 `release-closeout`）；
    步骤 4 按失效规则交接；主链在本 intent 外补验与增量 code-review 后再重跑本步。
- 准备 `--closures-json`，覆盖每个 child Change outcome，并可补录未写 child Change 的对象；本步不写对象。
  - 本 release/hotfix 上直接修复、尚无 child Change 的 Bug 必须补录入 closures。
- 准备 `--deferred-acceptance-json`：对象，键为 Bug ID。
  - major 且 resolution 为 `deferred` 或 `wont-fix` 时须含 `accepted: true`、
    非空 `reason` 与非空 `follow_up`；无此类 Bug 时传 `{}`。
- 运行 `list --repo "$REPO_ROOT" --type bug --status open --status fixed --status rejected`：
  - 待分类：`found_in: unreleased` 且非 duplicate；不翻对象目录。
  - duplicate 不进 outcome。对每项按表分类：

| 分类 | 处理 |
| --- | --- |
| `fixed` | 须由 bug close 关闭并写 `fixed_in`；CLI 仅核对 closed 与版本一致 |
| rejected | 使用既有 reject-reason |
| deferred | 保持 open |
| duplicate | 不进 outcome，canonical 与 duplicate 一并归档 |

- 可选加速（见 `common.md`「Jev 可选加速」）：
  - 仅歧义且 tool 可用。❌ 不调：bug close 已通过的 `fixed`；
    已有非 duplicate reject-reason 的 `rejected`。
  - 调用：`choice`/`run`；选项同表键加 `ask`；state = 摘要与证据。
  - 采信：`fixed` 仅 bug close 已通过；`rejected` 仅已有
    reject-reason；否则未采信。落入上表。
  - `ask`/未采信→主 Agent，必要时询问。❌ 不代填
    deferred-acceptance，不放宽下方 critical/major。
- 📌 critical 仅 fixed；major deferred/wont-fix 要用户接受、理由和 follow-up。
- 验收：完整 closures 与验证、接受记录。

**收口** <a id="s8"></a>

- 调用 `release-closeout`：
  - 传入步骤 7 的 `--closures-json` 与 `--deferred-acceptance-json`。
  - hotfix 另传 `--hotfix-change-json`；两者均传 `--release-date`。
  - 版本根 Change 聚合 child outcomes/evidence，evidence 按首次出现顺序去重并追加 manifest 验证命令。
  - CLI 操作前要求 clean；主动提交本次必要材料，不夹带无关改动。
- 运行实际收口：
  - CLI **只复用**可复用的 `verify.branch.json`（声称通过且命令序列一致）写入版本
    Change；❌ 永不在 closeout 内执行验证命令 / release suite。
  - 不可复用 → CLI 失败（`verify_full_not_reusable`），停止交接；主链外补 verify。
- 验收：CLI 退出 0、收口产物和完整 diff。
  - 退出 0：读 stdout。`verification.reused` 为复用路径（非 null）。
  - 非零：读 stderr 最后一行 JSON，不为查看原因重跑 closeout。
- 通过条件：成功到 9。
- 异常与交接：失败保留现场并停止，报告命令结果与实际写入。
  - post-validation 失败时，该 JSON 的 `details.findings` 与 `details.written` 即原因与已落地写入。
    不为查看原因再运行 doctor。

### 提交与 Gitflow

**交接** <a id="s9"></a>

- 由 Agent 复核并提交本次事实、Change、收口材料与阶段证据，同次继续。
- 按分支：
  - feature/bugfix 不 push，核对 objectives 与所需 report 已交后进入本地 Gitflow 合并。
  - release/hotfix 仍需已提交收口结果，finish 将发版推送到 origin。
  - feature/bugfix 必须有规范 child Change。
- 再次核对 report 仍已交（存在且声称通过）；收口期间若改了实现或 report 失效：
  **停止并交接**，须在本 intent 外补 verify / code-review 后再续办；
  ❌ 不回委托 verify/full。不做 commit 对齐审判。
  - release/hotfix 已收口，按步骤 4 的已收口规则核对 `changes/<semver>/`。
  - report 缺失时停止，不进入步骤 10。
- 成功收尾前将 `objectives.md` 的 close-out 项改为 `[x]` 并提交（材料仍在 unreleased 时）。
- 再次核对步骤 2 的目标主线仍被最终 HEAD 包含；主线前进时：
  - feature/bugfix 回到步骤 2 重新集成、审查并更新事实材料。
  - release/hotfix 无论是否已收口均停止并报告状态不一致，不重新集成、不覆盖版本目录。
- 核对 clean 与当前证据后进入 Gitflow 合并，不自动处理无关改动。
- 验收：必要提交、当前 clean 和交付条件。

**合并** <a id="s10"></a>

- 执行关口：
  - 由 `$mdf deliver --auto-pilot` 委托时，未带 `--yolo` 且步骤 9 通过：
    - 必须返回 deliver 步骤 6，待其取得确认后才执行本步骤；不得自行调用 `finish-gitflow`。
  - 由 `$mdf deliver --yolo` 委托时步骤 9 通过后直接执行本步骤，不返回确认。
  - 独立 `$mdf close-out`（`$mdf finish` 同义） 与默认 `$mdf deliver` 不增加该关口。
- 调用 `finish-gitflow --repo "$REPO_ROOT"`：
  - feature/bugfix 不 fetch、不 push；no-ff 合并到本地 develop；角色分支仍在则失败。
  - release/hotfix 要求 origin；首次调用 fetch 后要求本地 master/develop 与远端一致。
    - no-ff 合并到 master，创建注释 `v<semver>` tag（正文为本版 CHANGELOG
      精简条目），再 no-ff 合并 master 到 develop。
    - 原子 push `master`、`develop` 与 tag。不推送、不删除远端 `release/*`/`hotfix/*`。
  - 合并/发布成功后，将源 worktree 切为 `detached HEAD`，删除本地源分支，保留工作区后退出。
- 验收：合并、源分支删除、保留工作区的 detached 状态、tag 与（release/hotfix 的）推送结果。
- 异常与交接：停止并报告当前分支、已完成合并、tag 与推送状态。
  - 冲突时 CLI abort 当前 merge，但不得声称此前已完成的合并也被回退。
  - 不继续推送或删分支；询问用户是否继续。继续或未决回步骤 10，用户停止则停止。
  - 必要修复按确认范围由 Agent 复核并提交。

工作区清理（Gitflow 成功后）：
- 先核验、完成所有收尾并报告；删除工作区不是 close-out 完成条件。
- deliver 委托时先返回，由其步骤 5 完成核验、Goal 与报告后执行本节。
- `retained_worktree` 为 null 或指向主 worktree 时不删除主工作区。
- 否则展示绝对路径，询问是否删除；所有模式（含 `--auto-pilot`、`--yolo`）都须明确答复。
  - 说明：删除后本对话不要再继续，后续工作在主 worktree 开新对话。
  - 拒绝或未决则保留，不影响交付完成。
- 确认后直接执行 `git -C <主路径> worktree remove <保留路径>`，不引入另一个脚本。
  - 从主 worktree 启动，作为最后一次 tool call；成功后只报告删除结果并结束本对话。
  - 不加 `--force`；失败则保留现场并报告，不重跑 finish。

release/hotfix 首次发布前，CLI 保存发布进度记录：
- 位置：Git common dir 的 `mdf/finish/<完整分支名>.json`；含源提交、origin、目标起点与进度。
- 源 worktree 已 detached、已删除或已切分支时，从主 worktree 续办：
  `finish-gitflow --repo <主路径> --source <原分支>`。
- 脚本逐项核对记录与实际本地/远端引用，跳过已完成合并与 tag。
  - 推送结果丢失时先查询远端，完全一致则仅继续清理。
- release/hotfix 分支存在期间 develop 可继续前进：
  - 续办时若 develop 尚无合并记录且本地与 origin/develop 一致，
    以当前 develop 刷新记录中的合并基线，再 no-ff 合并 master。
  - 精确匹配原基线与 master 双亲的未记录合并直接恢复，不重复合并。
  - master 仍严格核对原基线；最终原子推送前的远端校验使用刷新后的 develop 基线。
- 记录、源提交、origin 或目标引用冲突时返回 `publish_state_changed`：
  - 停止并报告，不重置分支、不覆盖 tag、不盲目重推。
