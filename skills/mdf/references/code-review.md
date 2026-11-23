# Code Review

## 审阅核与参数

同一次审查走同一条链。`--read-only` 跳过修复与返工。没有 `--output` 时不写结论文件，会话里的结论仍要给出。

`检查 worktree → resolve-base → 统计 diff 行数 → 派发 → 审查 → [Repair] → [Record] → 结论 → [文件]`

拒绝审查、不审查、以及因 subagent、diff 大小或 path 数量停住，都不是合法结果。

- clean 时固定右端点为当前 `HEAD`。交付模式 dirty 时一并审查暂存、未暂存及相关未跟踪文件，
  审查结束后保留原 clear commit。显式 against 与只读旁路要求 clean。
- 强制覆盖 paths = sourceset ∩ ¬module-ignore 的实现变更；文档/配置/交付材料不进覆盖清单，reviewer 可读不禁。
- `$mdf code-review --against <commit>`：用该 commit 覆盖本轮左端点（完整 SHA），仍要求 clean。
- `$mdf code-review --read-only`：不进入 Repair 与 Record，不修、不返工、不勾 objectives。
- `$mdf code-review --output <path>`：把已经给出的结论再写入该文件。没有该参数则不写文件。
- `--against` / `--read-only` / `--output` 可组合；未传 `--against` 时按下方 resolve-base 自动选左端点。
- 无账本且没有 `--read-only` 时执行 [无账本审查](code-review-adhoc.md) 并返回。单独 `--against` 只覆盖左端点，不因此跳过修复。

### 派发

有冻结 roster 时按 roster.reviewers 与 review_strategy。close-out 集成增量轮与主链 verify 修绿轮为 1。

没有 roster 时只统计 diff 行数，不输出 diff 正文。
行数是过滤后 paths 的 `git diff --numstat` 新增与删除之和。
人数为 `ceil(行数 / 1000)`；行数为 0 且 paths 为空则不派发，结论为 pass。
paths 非空而行数为 0（含 numstat 的 `-`）时派 1 人，覆盖全部 paths。人数只决定派几个。
没有 roster 且人数大于 1 时才切开：按 `.mdf/modules.yaml` 的模块归属分组，同模块不拆开。
其次按目录相近合并或分开。组数少于人数时少派，不拆模块去凑人数。每人只审自己那组，并集必须盖住全部 paths。

人数优先级：人工 feature、有账本 adhoc，以及指定为 1 的增量轮，然后冻结 roster，然后无 roster 的行数。
有账本但 roster 未冻结则停止。`--read-only` 读不到冻结 roster 时改按行数，不停止。

派不出 subagent（当前已是 subagent、没有工具或环境限制）时，由主 Agent 审查尚未覆盖的 paths。已经是 subagent 的执行者就地审完自己的一组，不再向下派发。不得因派发失败拒绝审查。

### resolve-base

| 情形 | 本轮左端点 |
| --- | --- |
| 显式 `--against` | 解析后的完整 SHA |
| 交付有可用 clear commit | `review-prepare` 返回的 clear commit |
| 无可用 clear commit；feature·bugfix·hotfix·adhoc | branch start（`delivery.json.start_commit` 或 `branch.*.mdf-start-commit`） |
| 无可用 clear commit；release | 上一正式发布 master commit/tag，首次发布传 `--initial-base` |

报告上下文可另保留 `delivery_base`（整次交付起点），与本轮左端点分离。

## 决策树

一条链。`--read-only` 不进入步骤 3 和 4。没有 `--output` 时步骤 5 不写文件。

```text
┌──────────────────────────────────┐
│ 1 Check                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 只读                 ────→ 2 Review
                 ├──── 无账本 adhoc         ────→ [无账本审查并返回]
                 ├──── 来源 verify 且待修绿 ────→ [返回原 verify；独立调用报告待续办]
                 ├──── 已齐审查且修复续办   ────→ 3 Repair
                 ├──── 已齐审查但勾选未完成 ────→ 4 Record
                 ├──── 失败或缺失           ────→ [停止并报告]
                 │
                 ▼ 新审查、增量新一轮或首轮未齐
┌──────────────────────────────────┐
│ 2 Review                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 未覆盖           ────→ [留在 2，主 Agent 补审]
                 ├──── 只读             ────→ 5 Report
                 ├──── 可以复用         ────→ 4 Record
                 │
                 ▼ 交付审查完成
┌──────────────────────────────────┐
│ 3 Repair                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 修复或验证可修     ────→ 3 Repair
                 ├──── 需要用户决定       ────→ [保留现场并报告]
                 ├──── 外部条件或无法继续 ────→ [保留现场并报告]
                 │
                 ▼ finding 已裁定且无阻断项
┌──────────────────────────────────┐
│ 4 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── close-out 委托且需 smart ────→ [交接主链外续办修复窗]
                 ├──── smart 失败且可修         ────→ 3 Repair
                 ├──── 其他失败或缺失           ────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 5 Report                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 只读且 context 已变化 ────→ 2 Review
                 ├──── 有 --output ──────────────→ [写入文件后结束]
                 └──── 无 --output ──────────────→ [结束；会话结论已给出]
```

步骤 2 先运行 `review-prepare --repo <repo> [--against <commit>] [--initial-base <commit>] [--force]`。
命令返回实际左端点、未审增量、`numstat`、人数与 project rule。默认按 clear commit 比较两端，
不要求 ancestor；缺记录或规则变化则回到正常范围。绑定父流程的固定补审范围用 `--against <commit> --force`。
`skip_review: true` 时直接进步骤 4，终稿写明无须复审的依据。dirty 仍 load，按实际 worktree 审查，不能跳过。

仅 `--read-only` 或显式 `--against` 再调用 `review-context`，日志在 checkout 外。
派发按「派发」。未覆盖留在步骤 2，由主 Agent 补审。只读从步骤 2 进入步骤 5。交付审查完成后进入步骤 3。

## 工作流（唯一执行契约）

步骤 1–5 是同一条链。审查规则见 [Review 协议](reviewer-protocol.md)。派发只在步骤 2。
外部报告须核对固定范围、rule、冻结份数和覆盖；不符时仅作补充，不凭 CI pass 自动勾选。

交付模式读取 `references/common.md` 与 `references/delivery-contract.md`；涉及 PRP 或 Bug 时读取 `references/object-contract.md`。
`--read-only` 只核 Git 根并执行「上下文与报告」，不跑交付前置，审查仍走步骤 2。显式 `--against` 只覆盖左端点，不跳过修复。

- 读取 [项目阶段 rule 契约](project-rules.md)，本阶段按 merge 后规则执行，冲突时 project 优先。
- CLI 使用 `python3 "$MDF_ROOT/scripts/mdf.py"`；`--read-only` 或显式 `--against` 的 review-context 用 `python3 -B`。
- 独立调用只推进当前 intent；deliver 内部委托时完成后返回调用方，由其选择下一阶段。
- close-out 内部委托时返回 close-out；需要 smart 时返回待主链外续办，不在该调用内补验或 fact。
- 主链 verify 内部委托时，本 intent 走完步骤 5 Report 后返回原 verify 的修绿步骤（verify 步骤 5）；不接管父阶段的 branch/smart 勾选。
- 覆盖终稿时不得删除 objectives 中父 verify 的非 checklist 续办备注。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check | 约束 | 检查 worktree、分流；只读记下跳过修复 | 参数或范围、rule、报告 | 只读仍2；verify待修绿返回；漏勾4；修复续办 3；否则 2 | 停止并报告 |
| 2 | Review | 约束 | 按 scope 审完全部 paths；派不出则主 Agent 审 | 增量、覆盖 | 只读5；可复用4；否则3 | 未覆盖留在2 |
| 3 | Repair | 约束 | 主 Agent 裁定、修复、整理 tests 并复核 | 裁定、修复与 suite 验证，无阻断项 | 4 | 可修则留在 3；否则保留现场并报告 |
| 4 | Record | 约束 | 按需 smart；洗成无 commit 终稿并勾选 | 终稿、smart、提交 | 5 | close-out 需 smart 返回待续办；可修则 3；否则停 |
| 5 | Report | 约束 | 会话给出结论；有 `--output` 才写入经校验的 JSON | 结论、可选文件 | 结束 | 只读 context 变回2；交付不回2；无 `--output` 不写文件 |

close-out 或主链 verify 已将 code-review 退回 `[ ]` 且传入或保存左端点时，按该范围开启增量新一轮。
旧终稿或目标主线已包含都不代替此轮；进行中草稿只存范围和审查证据，进度仍看 objectives。

## 术语与数据结构

### 上下文与报告

仅 `--read-only` 或显式 `--against` 在步骤 2 调用 `review-context --repo <repo> --against <commit>`。步骤 5 在会话中给出结论。
CLI 只提供确定性 context；前缀 `python3 -B "$MDF_ROOT/scripts/mdf.py"`；日志与报告在 checkout 外。
步骤 2 按「派发」审完全部 paths。派不出 subagent 时主 Agent 补审。拒绝审查不是结果。
步骤 5 在 `--read-only` 时用 [独立报告 schema](../assets/templates/against-review-report.schema.json)。`--read-only` 不进入 Repair，也不读「Findings 与裁定」做 owner 裁定。

- against 为固定 SHA，与当前 HEAD 直接比较，不算 merge-base；worktree 必须 clean。
- rules / sourceset / module ignore 读当前 HEAD；强制 paths = sourceset ∩ ¬module-ignore。
- 不接受交付、review-base、previous-report 或 backend；无需 ready 或本地交付材料。
- `--read-only` 不改 HEAD/index/refs/objects；不跑 hooks/filters/tests；不修、不 commit、不勾 objectives。单独 `--against` 仍可进入 Repair。
- findings 含位置、触发、影响、证据与 P0–P3。未审查不得写入 incomplete，也不得把 decision 写成 needs-review。
- context/report 记录 against、head、rules_sha256 与 context_sha256。
- `rules_sha256` 使用协议版本号，不使用 reviewer-protocol 全文。兼容修订不使上轮报告失效。
- `--read-only` 在步骤 2 保存 context.json；步骤 5 用原 against 重跑 review-context，核对 context_sha256 与 head。
  - 一致才出报告；否则回 2 重审；不复用旧通过结论；失败读日志报 error。
  - 交付进入过步骤 3 或 4 后，步骤 5 不再重跑 review-context，也不回步骤 2。
- `review-report-check` 校验最终报告；valid 才返回；`--output` 另存路径；不直接 approve/merge。

### 项目 rule 的阶段接入

步骤 1 切回 owner 并核对 ready 与范围后，以 `--stage code-review` 加载项目 rule，再判定续办。

- 本步在修复续办、无新改动和仅漏勾等快速出口前执行；规则变化不能沿用旧通过结论。
- 每次分派前核对 rule，每份任务在固定 opening 后完整携带 MDF rule 与 project rule 原文。
- reviewer 报告、进行中草稿与终稿记录来源、内容指纹；主 Agent 按相同规则裁定与修复。
- 已配置时验收每份报告的 rule 来源与指纹，缺失或不一致不得视为完整报告。
  - 未配置时以无项目 rule 核对，无需内容指纹。
- 步骤 4 与无新改动出口验收前重新加载核对，变化先停止说明并等待确认。
- 规则变化确认后走首轮：从固定交付基线审到新 review_head，使用冻结 roster.reviewers。
  - 不复用旧报告，不沿用原增量范围或修复窗；旧问题清单仍传入作复核上下文。

### 范围与前置条件

进入步骤 2 前，objectives 的 lint 项须已勾选并提交；增量轮核对最近验证中的 lint 结果。
交付模式支持 dirty 审查。固定 commit 的旁路仍须 clean；需要记录 clear commit 时先按公共规则提交待审内容。

本节确定审查人数、记录位置、轮次、固定基线与各分支前置条件。

无账本 adhoc 按 code-review-adhoc.md 执行；不套用本节的账本、roster 配置或勾选前置。
只有 `--read-only` 跳过步骤 3 与 4。显式 `--against` 不跳过修复。

- 步骤 1 支持 feature、bugfix、hotfix、release、adhoc；cwd 为 qa/dev 时切回 owner。
- 先确认目标仓库 ready，再用 `review-prepare` 确定本轮范围。
- 审查人数见「派发」。有账本时读取冻结 roster：
  - 有 `delivery.json` 时用 `delivery status`，否则读 `branch.<owner>.mdf-roster`；有账本但未冻结则停止。
  - 本轮应派人数在有 roster 时默认同 roster.reviewers。
  - close-out 集成或主链 verify 修绿产生的增量新一轮为 1，不改冻结 roster。
  - 无有效上轮记录而走首轮时仍用 roster.reviewers。
- 审查记录写在 `changes/unreleased/<slug>/code-review.md`：
  - PR mode 的 release/hotfix 若已准备 `changes/<version>/delivery.json`，本轮使用该版本目录的材料、objectives 和报告。
    PR/MR 合并前可补审修订；不另建 unreleased 副本。候选流程见 [PR](pr.md)。
  - feature/adhoc 用 delivery.json 的 slug；bugfix 用 Bug ID 的 kebab-case。
    release 与 SemVer hotfix 用分支版本；slug hotfix 用原 slug。
     已归档 hotfix 使用 `delivery status` 返回的版本目录，见 [Hotfix 版本](hotfix-version.md)。
  - 无该 Markdown 视为无记录。进行中可为带 tip 的草稿；裁定收口后覆盖为无
    commit 终稿。branch 验证证据是主链 `verification-report.json`，不写
    `code-review.verification.json`。
  - ❌ 不在 `docs/context/research/` 保存审查报告。

步骤 1 按已有记录判定本轮走向：

- 主链 verify 交接优先识别：已有有效上轮终稿与汇总清单，且传入了修复前左端点时，按 1 人增量处理。
  - 来源 verify 的草稿仍待修绿时，返回原 verify 修绿；不得提前派审查。
  - 草稿已待复审时固定 review_head；不能因存在新草稿误判为无首轮记录。
  - 未齐报告只补齐同一范围；无有效上轮时补完整首轮，不以 1 人替代冻结 roster。

- 首轮：无记录或仅有不完整草稿时走首轮；首次审查才固定当前 HEAD 为
  review_head（写入进行中草稿或仅会话/派发参数，供本轮操作）。
  - 首轮未齐时进入 2 补齐。报告未齐前不改审查对象。
  - 已出现新的交付改动也不重新固定 review_head，不重派。
  - 报告齐后进入修复窗，由步骤 3 复核原 review_head 以来的改动。
- 修复窗：本轮应派报告已齐，且修复终点尚未与当前代码指纹对齐。
  - 窗内只修复已记录问题，保留原 review_head，不覆盖原报告。
  - 直接进入 3。不开增量新一轮，不重派 subagent；不提前跑 verify branch。
  - 本轮若改了实现/测试/验证配置：步骤 4 按调用方边界处理 smart；失败且可修时只回 3。
- 修复窗在本轮修复已提交、且（若本轮改过实现、测试或验证配置）smart 已通过时关闭。
  - 此后改实现、测试或验证配置才可进入增量新一轮。
  - 主链 verify 修绿改动由 verify 记录原左端点，开启 1 人增量新一轮，不复用旧修复窗。
- 无新改动：按步骤 2 的 `skip_review` 决定是否免派发。已有终稿可作为本交付的裁定记录。
- 增量新一轮：修复窗已关闭（或终稿已在），且其后改了实现、测试或验证配置时进入
  （含 close-out 集成以及主链 verify 修绿后的增量）。
  - 完整上轮：应派份数报告已齐（或已有终稿）、已采纳与未解决问题清单齐全。
  - 操作左端点由 `review-prepare` 选择；close-out 集成用集成前 HEAD（当场记录）。
    pre-gitflow-finish 补审用其执行时返回的原 `before_head`，可从上下文或 CLI 日志恢复。
    主链 verify 修绿轮人数为 1；其他普通增量仍为冻结 roster.reviewers。
  - 重新固定 review_head 为当前 HEAD，进入 2。
  - 主链 verify 传入其修复前左端点；从已有草稿续办，不从新终稿提交倒推修复前范围。
  - ❌ 不得从 start_commit 重扫已审区间（走首轮时除外）。
  - 上轮残缺（缺份数、缺问题清单）时不得假装增量，停止并要求补记录。
    无记录走首轮。
- 范围无法判定时停止询问。
- 不得把未提交改动遗漏在审查范围外；存在无关改动且无法隔离时停止。

| 分支 | 固定基线 |
| --- | --- |
| feature、adhoc | delivery.json 的 start_commit |
| bugfix、hotfix | start 保存的 `branch.<完整分支名>.mdf-start-commit` |
| release | 上一正式发布版本的 master commit/tag，解析为完整 commit hash |

基线读取与审查区间：

- bugfix/hotfix 用 `git config --local --get "branch.<完整分支名>.mdf-start-commit"` 读取起点。
- release 首轮依据正式发布记录确认上一版本，核对其 `v<version>` tag 指向的 commit 位于 master 历史。
  - PR 候选已更新本地 manifest 时，从目标 master 的正式发布记录确定上一版本，不取候选 latest_release。
  - 不取 master 合回 develop 的合并提交，也不使用移动的 master/develop HEAD 代替发布基线。
  - 首次发布没有上一版本时，须用户明确确认初始基线。
  - 基线缺失、歧义或对象不可解析时停止询问。
- clear commit 与 review_head 直接比较，不要求 ancestor。
- 审查内容：
  - 首轮：`git diff <base_commit> <review_head>`，按 sourceset ∩ ¬module-ignore 过滤。
  - 增量：`git diff <操作左端点> <review_head>`（操作左端点按上方规则，不读终稿
    hash）。
  - 强制覆盖仅为实现变更；文档/交付材料不进 paths，可读不禁。
  - 并读取必要上下文，不能仅按提交标题或文件名审查。
- release 正常范围从上一版本开始。存在可用 clear commit 时以该 commit 比较两端；没有相关变化即跳过。
- 后续轮次只覆盖操作左端点以来的增量，仍须复核上轮问题。
- 步骤 1 仅在新审查或增量新一轮时将本轮左端点与 review_head 记入进行中草稿
  （或派发参数），明确尚未通过，再启动审查。
- 交付起点 base_commit 在本轮操作中固定，续办沿用，不重新追随分支或 tag；
  裁定收口写入终稿正文时不得保留任何 commit hash；父 PR 返工备注按步骤 4 单列保留。

各分支前置条件：

- 人工 feature：仅要求用户显式勾选人工工作，不要求 converge；使用 1 个 reviewer。
- adhoc：工作项已勾即可，不要求 converge；使用 1 个 reviewer。
  - 目标取自 delivery.work；重开审查时退勾 code-review 及后续项，成功后仅勾本项。
- [修复移植](fix-pick.md)：objectives 的 pick 须已勾；按本次 roster 审查。
- 其他交付进度只认 `objectives.md`：converge 项须已 `[x]`（含 start 对 `has_dev: no` 的预勾）；
  未勾停止，提示先 `$mdf converge`。
  - `needs_design: yes` 时可读 design.md 作审查上下文；不以 design/converge gate 文件为通行证。
  - 修复续办进入 3；步骤 4 按需补 smart，不在本 intent 强制 verify branch。
- release 读取 `objectives.md` 对照本版目标与验收；超出计划的新能力不在本轮实现。
  - 依本节规则选择 clear commit 或上一正式发布基线。
  - 📌 integrate 项须已 `[x]`；未勾停止，提示先 `$mdf integrate`（或不联调应由 start 预勾）。
  - 📌 联调时（含 collab-mode），进入 2 前须双端验收通过，且已确认计划内开发与联调改动已完成。
    此确认不禁止本轮审查或后续 verify 的代码修复；修复按对应阶段复审与验证。
    未双端验收通过则不派审查。
- hotfix/bugfix 读取 `objectives.md` checklist 与对应 Bug。
- bugfix 的 `suites.json` 在后续 verify branch 前关联；本步不强制。

### 独立审查

本节是步骤 2 的派发与审查，只读同样适用。`--read-only` 只跳过步骤 3 与 4。
主 Agent 派发 subagent 时，以下文为提示词 opening，并附上本次上下文与输出约束：

> 以最严苛的白盒测试专家视角审查实现代码和测试用例，主动挑战实现逻辑与测试的充分性，
> 寻找隐藏缺陷和覆盖盲区。以证据核实逻辑正确性与测试有效性，不因测试通过就认定实现正确。
> 严格只读 worktree，不写文件、不运行 tests；返回位置、触发条件、影响、静态证据和建议优先级，由主 Agent 核实。

派发：

- 步骤 2 按「派发」的人数优先级启动 subagent。指定为 1 的轮次不为冻结 roster 让路。
  只有没有 roster 且人数大于 1 时才按模块相近度切开，不按行数切。replicate 不按模块拆分。派不出则主 Agent 审，不得停止。
- `review_strategy` 默认 `replicate`：
  - 各审查者收到相同的交付 base_commit、本轮左端点、review_head、工作目录、目标、验收、
    适用设计材料与相关当前事实页。
  - 均覆盖本轮范围检查正确性、验收覆盖、测试质量、code smell、架构合理性及非必要复杂度。
  - 不安排分工，不按文件、模块或领域拆分，不共享其他审查者结论。
- 本轮只有 1 人时覆盖整个本轮 diff，不受冻结 partition 切片限制；仍核对相关旧 finding。
- 多人 `partition` 时 owner 按 design 已有切片或本步切开的范围派工，每人只审自己那片；
  仍不共享其他审查者结论。
- 覆盖冻结值与模型：
  - 调用可带 `--review-strategy` / `--code-review-model` 覆盖冻结值，派工前运行 `delivery roster` 写入。
  - roster.models 含 `code-review` 时写入该值，按口语描述现场解析；
    可多个模型，可分给本轮多名审查者。没有则不提。
  - ❌ 不得写入其他 intent 的模型。
- 增量新一轮还必须带上轮已采纳项与未解决项；不能只看新 diff 假装旧问题消失。
  - close-out 集成增量轮（1 人）只使用该已汇总清单，
    不得把上轮多份独立报告交给本轮 reviewer 自行合并。
- 已记载的当前行为以事实页为回归基线：与本次目标无关的行为变化按问题报告。
- 每份任务均包含 `modules.md` 的 ignore 条款以及 lint 工具报告；体积上限按实现变更核对。
  - 本地、against 与交付 CI 均将实现变更与 sourceset 求交，再排除 module ignore。
  - paths 与 diff 同步过滤；未归属实现不进入强制覆盖；文档与交付材料不进 paths。
  - 读取 lint 报告，按 `sourceset` 核对全部适用 module 的 `size_limits`；各字段默认 1000/50/70，未归属文件用默认策略。
  - 单文件行数与触及 package 的完整同类成员数分别满足各配置；package 实现/测试不相加。
  - 源代码/package 超限按各触发配置的 `split_percent` 向下取整验收。
  - 文件拆分按职责、依赖与适用设计模式审代码；不得把 `part1`、`part2` 或仅改名的机械切分验收为通过。
  - 合理设计可迁移入口；不得仅因入口改变或未在原位置保留 facade、re-export、转发壳而提出问题。
    核对设计依据、明确的对外契约，以及调用方、测试是否同步更新。
- 📌 reviewer 严格只读，不修改实现、tests、配置或报告，不运行 tests，不建立角色 worktree。
  - main Agent 在派发前核对 owner 与 review_head，完整传入规则与范围；reviewer 不调用会落盘日志的 MDF CLI。
  - reviewer 通过会话返回报告；main Agent 负责各份独立报告落盘，报告齐全前不修改审查对象。
  - main Agent 对照 HEAD 与 worktree diff 核对只读边界；发现越界改动则停止，保留现场并说明差异。
- 本轮进度由 main Agent 记录，不以 reviewer 写文件作为报告完成条件。
- main Agent 分派前用只读 measure_code.py 准备本轮范围的文件/package 实测数据；修复后由 main Agent 重测。
  - 仅读取 references/lint.md 的「审查只读测量」条款，不重新执行 lint 工作流。
  - 初审使用 --ref <review_head>；修改前使用 --ref <本轮左端点>，需原触发策略时显式传 --policy-ref <策略快照>。
  - 修复后使用 --ref <已提交修复终点 HEAD>，不覆盖本轮固定 review_head。

  - 数据通过任务原文或已有工具日志交给 reviewer，不让 reviewer 执行脚本、运行 tests 或写入报告。

### 缺陷复现

全部独立报告齐全后，由 main Agent 汇总去重，构建并运行 failing test，再裁定 finding。

- 步骤 3 由 main Agent 从目标、验收、设计或当前事实页确定预期行为，构建最小的自动化复现 test，优先放在 quick 层。
  - test 断言正确行为；不得断言错误行为、使用无条件失败或 mock 掉被审查逻辑来制造失败。
  - 复用已有 failing test 时也须亲自运行并核对失败原因，不要求重复编写同一用例。
- main Agent 的核实记录包含 test 路径或原文、运行命令、退出码、完整报告路径，以及预期与实际结果；未运行时不得编造执行结果。

| 复现结果 | 证据与去向 |
| --- | --- |
| 因所指行为缺陷失败 | 附失败报告，进入步骤 3 裁定与修复。 |
| test 通过 | 说明未复现；已有证据排除 finding 时建议不采纳，否则保留证据交步骤 3 降级裁定。 |
| test 或环境错误 | 由 main Agent 在步骤 3 修正复现方法；无法继续则记录尝试、限制及其他证据，交步骤 3 降级裁定。 |
| 无法构建 test | 说明原因与其他证据，交步骤 3 降级裁定；不得仅报告猜测。 |

- 步骤 3 汇总去重后按合并证据裁定，无有效 failing test 的 finding 按既有优先级降低一级，最低级仍保留。
  - 记录原级别、有效级别与降级理由；同一 finding 不因多份报告或续办重复降级，补齐有效 failing test 后按原级别重新裁定。
  - 级别与采纳决定分别记录，不因缺少 test 判为无效或直接不采纳；未定义优先级时按下表处理。

| 原级别 | 无 failing test 时的处理级别 |
| --- | --- |
| 必须修 | 建议修 |
| 建议修 | 待跟进 |
| 待跟进 | 待跟进（最低级） |

- code smell、架构、体积与文档类问题提供对应契约及实测或具体结构证据，不伪造 failing test。
  - 无法构建 failing test 时同样降一级；声称会导致错误行为时仍须尝试复现。
- 降级不豁免既定目标、契约或验证门槛；主 Agent 结合剩余证据裁定是否修复或待跟进，并记录理由。
  - 待跟进仅限不阻断既定验收的问题，单独列出，不混入未解决的阻断项。

报告内容（进行中 / 分报告）：

- 每份报告均声明审查种类（首轮 | 增量）、派发所用 tip（base / 左端点 /
  review_head）、已完成的审查范围及未完成项；无未完成项时明确写无。
- 增量轮次须有上轮问题复核表，逐项写明仍解决 / 复开 / 不适用。
- 发现问题时列出问题位置、触发条件、影响与证据；无问题时明确说明未发现问题。
- reviewer 为 finding 附建议原级别和静态证据；行为复现与降级记录由 main Agent 在步骤 3 补入草稿与终稿。
  - reviewer 没有 failing test 不影响报告完整性，也不提前触发降级。
- 代码规模以 lint 及只读测量数据为证据；reviewer 审查拆分职责、依赖及设计合理性，不重复手工计数。
  - lint 未通过时不得开始本轮审查；工具硬限制不得以 LLM 判断豁免。
  - 原超限拆分须保留触发时工具报告中的目标；修复后通过 --file-target/--package-target 传入所有原触发目标。
  - 适用结果须有 within_required_split_targets: true，且满足新位置硬限制；不能用迁入较宽松 module 后的目标替代原目标。

  - 只对本轮确属超限拆分结果的路径验该标记；未发生拆分的文件不能仅因超过拆分目标被要求改写。
  - 缺少适用结果的数据时由 main Agent 补测；无法取得证据则未完成，不把缺数据或空列表当通过。


报告验收：

- 主 Agent 核对每份报告与派发的左端点、review_head 和本轮范围一致，且无未完成项，
  才验收为完整报告。
- reviewer 提供位置、触发条件、影响、静态证据和建议优先级即可完成 finding 报告。
  - 证据或范围不足时退回补齐；复现是 main Agent 的职责，不能据此将 reviewer 报告列为未完成。
- 范围声明缺失、端点不一致或存在未完成项时，要求补齐；仍缺则主 Agent 重审该范围，不得因此结束。
- 不足应派人数、启动失败或结果缺失时，主 Agent 补审未覆盖范围。
  不得停止，不得把未审查写成结论。
- 续办只复用同一左端点与 review_head 的完整报告。未覆盖的 paths 不得进入修复；主 Agent 已补审的范围算已覆盖。
  - 增量新一轮不复用上轮分报告去覆盖新 diff；收口终稿另见步骤 4。

### 汇总、修复与复核

步骤 3 由主 Agent 汇总去重，逐项核实，记录采纳或不采纳的依据；以证据裁定，不按票数决定。

可选加速（见 `common.md`「Jev 可选加速」）：

- 时机：汇总去重后；tool 可用时。
- 每项：`score`（0=不采纳 / 1=建议修 / 2=必须修）。
- 收口：`choice`（`continue_fix` / `ready_to_close` / `need_human`）。
- state：问题摘要、证据指针与降级记录；score 是采纳建议，不代替 finding 的优先级，也不因降级自动减分。
- 采信后仍须主 Agent 核实依据并写入记录；未采信走原汇总。
- ❌ 不按 Jev 票数代替证据。

- 修复权限：
  - 允许自主修复实现，或依据已确认目标/设计纠正、补充、删除错误或重复测试，记录依据。
  - ❌ 不得削弱验收或验证门槛；目标/契约变更须用户确认。
- main Agent 在修复前按被测行为、依赖与 fixture 边界构建复现 tests，归入合适的现有 suite，必要时新建 suite。
  - 有效 test 纳入正式 regression tests；重复或错误 test 可合并、纠正或删除，逐项记录依据，完成临时文件整理。
  - 按既有授权边界同步成员选择、入口配置与 named suite 文档。
  - 移动或合并 test 时保留原缺陷断言与复现能力，记录 finding、正式 test、所属 suite 与执行报告的对应关系。
- 对采纳且复现成功的行为缺陷，在正式 test 位置确认修复前失败，再修复实现并运行同一 test 至通过。
  - 保留失败与通过报告，核对原失败原因已消除；不得通过削弱断言让 test 通过。
- 整理与修复后运行归属 suite 的正式入口，核对报告包含这些 tests。
  - 未被收集、仍有临时 test 未裁定或 suite 失败时留在步骤 3 修复；无法继续则保留现场报告，不进入步骤 4。
- adhoc 按 smart 选题核对覆盖；其余核对 design policy `suites` 或 `suites.json` 覆盖本轮功能块。
  缺漏按问题提出。
- 审查测试时核对 `delivery-contract.md`「失败语义」：
  - 无运行时 skip、提前返回或 xfail。
  - 入口配置能让 warning、skip 与空选择非零退出。
  - 豁免已记录且经用户确认。
  - 混合依赖的 test case 按问题提出，可依既定目标自主拆分，不得改成 skip。
- 更好的架构可以建议，超出目标不直接实施。
- 修复后由主 Agent 复核问题是否解决及是否引入回归，不强制再次启动审查 subagent。
  - 本步触及的代码与超限拆分读取 lint 与只读测量结果，核对目标标记并复核拆分职责。
- 同一范围内的修复、复核及 smart 循环留在步骤 3–4，不重新执行本轮多人审查。
  - 这是修复窗。报告已齐时不提前跑 verify branch、不开增量新一轮。
- 需要用户决定、外部条件或无法继续时报告阻塞，不记录通过的结果。

### 验证与持久证据

步骤 4：按是否改动实现、测试或验证配置决定是否跑 smart；裁定本 intent 可收口时洗成终稿。

- 本步不跑 verify branch（留给主链下一 intent）；也不写 `gates/code-review.json`。
- close-out 委托且本轮修复需要 smart 时，保留草稿与修复窗，返回「待主链外续办」；不运行 verify，不洗终稿、不勾选。
  - close-out 交接后，由 next/deliver 或独立 code-review 在主链外恢复本轮步骤 3–4；不重派已齐 reviewer。
  - 主链外完成 smart 与终稿后，再由原主链完成所需验证与 fact；旧通过报告不代替本轮结果。

本轮 smart 按以下互斥条件处理，不越过调用方边界。
失败修复后按 [增量验证契约](verify-incremental.md) 补测并汇总，不强制重跑整个 smart。

| 调用与改动 | 处理 |
| --- | --- |
| close-out 委托且本轮修复改了实现/测试/验证配置 | 返回待主链外续办，保留修复窗，不洗终稿 |
| 其他调用且本轮改了实现/测试/验证配置 | 跑 `$mdf verify --scope smart`；失败回 3 修 |
| 本轮未改实现/测试/验证配置 | 跳过 smart |

- close-out 集成后的增量审查仍按下方「close-out 核对」；branch 验证证据由主链
  `verification-report.json` 负责，不在本步伪造。
- ❌ 不能用仅检查文档结构的 strict validation 代替业务验证。
- 非 quick 用例在 converge 之后失败且本轮触及：
  - 必须尝试补一条 quick 复现用例。
  - 结果写入终稿「quick 复现」字段。

进行中草稿（未裁定收口前）可按轮保留 tip，便于续办；每轮操作内容包括：

- round、审查种类（首轮 | 增量）、base_commit、左端点、review_head。
- 本轮应派人数份独立审查及其身份、本轮新发现、上轮问题复核表。
- 逐项裁定、修复与复核、本轮修复终点 tip。
- smart（已跑 <命令/路径> / 未改实现、测试或验证配置跳过）。
- quick 复现（已补 <用例位置> / 未补 <原因> / 无非 quick 失败）、未解决项。

裁定收口（所有 finding 已裁定、无未解决阻断项，且若本轮改过实现、测试或验证配置则 smart 已通过）时：

1. 合并各轮/各份进行中材料，在本轮已定位的交付材料目录覆盖写入一份
   `code-review.md` **终稿**（**report**，非 gate）；候选发布沿用版本目录。
2. 终稿须含：结论（声称通过）、已采纳与未解决清单（未解决须为空）、各轮要点与
   裁定摘要、smart、quick 复现；路径与证据指针用仓库相对路径，不用 commit hash。
   - 复现成功的采纳项关联正式 regression test、所属 suite 及修复前失败、修复后通过的报告。
   - 无法构建 failing test 的 finding 保留降级、替代证据和最终裁定；待跟进项说明后续处理，不伪记为已修复。
3. rule 内容指纹须明确标注，不属于 commit hash；终稿保留该证据。
   ❌ 终稿不得出现任何 commit hash（含 base_commit / review_head / final_head /
   左端点 tip、完整或缩写 SHA）。本条仅约束审查正文；父 PR 返工备注单列保留恢复所需 SHA。
4. 进行中带 tip 的段落不得留在终稿；分报告已合并后不再作为核对对象。
5. 提交终稿；有账本时将 `objectives.md` 的 code-review 项改为 `[x]` 并提交。
   - 完整审查并提交后调用 `review-record --repo <repo> --against <本轮左端点> --head <已审并通过的最终 HEAD>`。
     首次 release 另传 `--initial-base <已确认基线>`。跳过、只读或 dirty 轮保持原 clear commit。
   - clean 轮有阻断项时，以本轮固定 HEAD 调用同一命令并加 `--failed`，使同内容的旧 clear 失效。
   - 只清理本轮审查草稿；不得删除父 PR 返工备注，完成后按其返回位置交还调用方。
6. ❌ 报告未齐或仍在修复窗时不得洗稿、不得勾选。

- ❌ 不运行 `delivery record --stage code-review`；不以 gate 文件为进度。
- 语义审查由 Agent 负责；CLI 不推理各份结论。
- 首轮未写清已采纳/未解决问题清单时，第二轮不得增量，停止并要求补记录。
- 主链 verify 修绿改了代码：内部委托本 intent 做 1 人增量审查，完成后返回 verify；范围与复跑规则见 verify。
- 勾选后又改实现/测试/验证配置：终稿作废，重新进入本 intent（增量或首轮），再出新终稿。

close-out 核对：

- 终稿存在且声称通过；已采纳/未解决清单齐全（未解决为空）。
- 不使实现审查过期、也不强制重开审查的改动（事实仍须另审）：
  - 记录文件自身、纯事实、收口文档。
  - local close-out 集成引入的非本交付 `docs/` 改动；PR mode 的远端集成不适用此豁免。
- close-out 集成 develop/master 产生新提交后：
  - local 模式仅非本交付 `docs/` 增量不新开审查；按 close-out 契约追加跳过说明。
  - PR mode 的每次远端集成都补审补测，按 `pr.md` 执行，不因仅文档或空 tree diff 跳过。
  - 其他集成增量一律作为增量新一轮从 1 开始，左端点为集成前 HEAD（当场记录）。
    - 以集成后的 HEAD 重做 1 份本轮范围审查；需 smart 时按上方边界交接，不复用集成前终稿当增量差。
    - 本轮完成后再次洗成无 commit 终稿并勾选。
  - 无有效上轮（无终稿或清单残缺）时按首轮从交付起点审到集成后 HEAD，人数仍为
    roster.reviewers。
- 记录或提交失败时保留现场并报告；不把阶段提交视为审查通过。
