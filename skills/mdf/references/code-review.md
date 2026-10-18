# Code Review

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 已齐审查且修复续办 ──────→ 3 Repair
                 ├──── 已齐审查但勾选未完成 ────→ 4 Record
                 ├──── 已齐审查且无新改动 ──────→ [结束]
                 ├──── 失败或缺失 ──────────────→ [停止并报告]
                 │
                 ▼ 新审查、增量新一轮或首轮未齐
┌──────────────────────────────────┐
│ 2 Review                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 审查未完成 ────→ [停止并报告]
                 │
                 ▼ 本轮审查完成
┌──────────────────────────────────┐
│ 3 Repair                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 需要用户决定 ──────────→ [保留现场并报告]
                 ├──── 外部条件或无法继续 ────→ [保留现场并报告]
                 │
                 ▼ 有效问题已解决
┌──────────────────────────────────┐
│ 4 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── smart 失败且可修 ────→ 3 Repair
                 ├──── 其他失败或缺失 ──────→ [停止并报告]
                 │
                 ▼ 通过
                 [结束]
```

## 工作流（唯一执行契约）

读取 `references/common.md` 与 `references/delivery-contract.md`；
涉及 PRP 或 Bug 时读取 `references/object-contract.md`。
读取 [项目阶段 rule 契约](project-rules.md)，本阶段按 merge 后规则执行，冲突时 project 优先。
CLI 使用 `python3 "$MDF_ROOT/scripts/mdf.py"`。
独立调用只推进当前 intent；deliver 内部委托时完成后返回调用方，由其选择下一阶段。
close-out 内部委托时完成后返回 close-out，继续材料与 Gitflow（不内嵌 fact）。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check | 约束 | 核范围、前置、项目 rule 与续办 | 基线、报告、rule 原文与指纹 | 仅漏勾则 4；修复续办 3；无新则结束；否则 2 | 停止并报告 |
| 2 | Review | Subagent | 按 roster.reviewers 启动独立 subagent 覆盖本轮 | N 份完整审查 | 3 | 停止并报告 |
| 3 | Repair | 约束 | 主 Agent 汇总裁定、修复并复核 | 发现、裁定、修复依据 | 4 | 保留现场并报告 |
| 4 | Record | 脚本 | 按需 smart；裁定收口则洗成无 commit 终稿并勾选 | 终稿、smart、提交 | 结束 | 可修则 3；否则停 |

close-out 已将 code-review 退回 `[ ]` 且传入或保存集成左端点时，按该范围开启增量新一轮。
旧终稿或目标主线已包含都不代替此轮；进行中草稿只存范围和审查证据，进度仍看 objectives。

## 术语与数据结构

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

本节确定审查人数、记录位置、轮次、固定基线与各分支前置条件。

- 步骤 1 支持 feature、bugfix、hotfix、release、adhoc；cwd 为 qa/dev 时切回 owner。
- 先确认目标仓库 ready，读取已有审查记录，识别相关未提交改动并按公共规则提交。
- 审查人数取冻结 roster.reviewers：
  - 有 `delivery.json` 时用 `delivery status`，否则读 `branch.<owner>.mdf-roster`；未冻结则停止。
  - 本轮应派人数默认同 roster.reviewers。
  - finish 集成产生的不可跳过增量新一轮为 1，不改冻结 roster。
  - 无有效上轮记录而走首轮时仍用 roster.reviewers。
- 审查记录写在 `changes/unreleased/<slug>/code-review.md`：
  - feature/adhoc 用 delivery.json 的 slug；bugfix 用 Bug ID 的 kebab-case。
    release/hotfix 用该分支的稳定 SemVer，不用 slugify。
  - 无该 Markdown 视为无记录。进行中可为带 tip 的草稿；裁定收口后覆盖为无
    commit 终稿。branch 验证证据是主链 `verification-report.json`，不写
    `code-review.verification.json`。
  - ❌ 不在 `docs/context/research/` 保存审查报告。

步骤 1 按已有记录判定本轮走向：

- 首轮：无记录或仅有不完整草稿时走首轮；首次审查才固定当前 HEAD 为
  review_head（写入进行中草稿或仅会话/派发参数，供本轮操作）。
  - 首轮未齐时进入 2 补齐。报告未齐前不改审查对象。
  - 已出现新的交付改动也不重新固定 review_head，不重派。
  - 报告齐后进入修复窗，由步骤 3 复核原 review_head 以来的改动。
- 修复窗：本轮应派报告已齐，且修复终点尚未与当前代码指纹对齐。
  - 窗内只修复已记录问题，保留原 review_head，不覆盖原报告。
  - 直接进入 3。不开增量新一轮，不重派 subagent；不提前跑 verify branch。
  - 本轮若改了实现/测试/验证配置：步骤 4 跑 smart；失败且可修时只回 3。
- 修复窗在本轮修复已提交、且（若本轮改过实现、测试或验证配置）smart 已通过时关闭。
  - 此后改实现、测试或验证配置才可进入增量新一轮。
  - 主链 verify branch 的修绿改动不打开本修复窗（由 verify 自行架构审视）。
- 无新改动：已有声称通过的终稿（或本轮已可收口）、无待修问题，且相对操作左端点到
  HEAD 没有新的交付改动时，核对后结束。
  - 不进入 2。
  - 此出口另须 objectives 的 code-review 已勾且已提交；仅漏勾或未提交则进 4 补齐。
  - 记录文件、纯事实、收口文档、以及非本交付 `docs/` 不是新的交付改动。
- 增量新一轮：修复窗已关闭（或终稿已在），且其后改了实现、测试或验证配置时进入
  （含 close-out 集成后的不可跳过增量；不含主链 verify branch 修绿）。
  - 完整上轮：应派份数报告已齐（或已有终稿）、已采纳与未解决问题清单齐全。
  - 操作左端点不从终稿读 hash：close-out 集成用集成前 HEAD（当场记录）；其它增量用
    终稿落盘提交 `git log -1 --format=%H -- <code-review.md>`；无法判定则走首轮。
    pre-gitflow-finish 补审用其执行时返回的原 `before_head`，可从上下文或 CLI 日志恢复。
    人数仍为冻结 roster.reviewers。
  - 重新固定 review_head 为当前 HEAD，进入 2。
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
  - 不取 master 合回 develop 的合并提交，也不使用移动的 master/develop HEAD 代替发布基线。
  - 首次发布没有上一版本时，须用户明确确认初始基线。
  - 基线缺失、歧义或对象不可解析时停止询问。
- 📌 基线必须是当前 HEAD 的祖先。
- 审查内容：
  - 首轮：`git diff <base_commit> <review_head>`。
  - 增量：`git diff <操作左端点> <review_head>`（操作左端点按上方规则，不读终稿
    hash）。
  - 并读取必要上下文，不能仅按提交标题或文件名审查。
- release 首轮覆盖上一版本以来的完整变化：
  - 不得仅审 release 分支创建后的改动，也不得因某个 child 已审查而跳过其代码。
- 后续轮次只覆盖操作左端点以来的增量，仍须复核上轮问题。
- 步骤 1 仅在新审查或增量新一轮时将本轮左端点与 review_head 记入进行中草稿
  （或派发参数），明确尚未通过，再启动审查。
- 交付起点 base_commit 在本轮操作中固定，续办沿用，不重新追随分支或 tag；
  裁定收口写入终稿时不得保留任何 commit hash。

各分支前置条件：

- 人工 feature：仅要求用户显式勾选人工工作，不要求 converge；使用 1 个 reviewer。
- adhoc：工作项已勾即可，不要求 converge；使用 1 个 reviewer。
  - 目标取自 delivery.work；重开审查时退勾 code-review 及后续项，成功后仅勾本项。
- 其他交付进度只认 `objectives.md`：converge 项须已 `[x]`（含 start 对 `has_dev: no` 的预勾）；
  未勾停止，提示先 `$mdf converge`。
  - `needs_design: yes` 时可读 design.md 作审查上下文；不以 design/converge gate 文件为通行证。
  - 修复续办进入 3；步骤 4 按需补 smart，不在本 intent 强制 verify branch。
- release 读取 `objectives.md` 对照本版目标与验收；超出计划的新能力不在本轮实现。
  - 审查基线仍为上一正式发布。
  - 📌 integrate 项须已 `[x]`；未勾停止，提示先 `$mdf integrate`（或不联调应由 start 预勾）。
  - 📌 联调时（含 collab-mode），进入 2 前须双端验收通过，且已确认此后不再改代码。
    未双端验收通过则不派审查。
- hotfix/bugfix 读取 `objectives.md` checklist 与对应 Bug。
- bugfix 的 `suites.json` 在后续 verify branch 前关联；本步不强制。

### 独立审查

主 Agent 向每个审查 subagent 派发任务时，必须以以下文字作为提示词 opening，
随后提供本次审查上下文及现有执行与输出约束：

> 以最严苛的白盒测试专家视角审查实现代码和测试用例，主动挑战实现逻辑与测试的充分性，
> 寻找隐藏缺陷和覆盖盲区。以证据核实逻辑正确性与测试有效性，不因测试通过就认定实现正确。

派发：

- 步骤 2 按本轮应派人数启动独立 subagent。默认为冻结的 roster.reviewers；finish 集成增量轮为 1。
- `review_strategy` 默认 `replicate`：
  - 各审查者收到相同的交付 base_commit、本轮左端点、review_head、工作目录、目标、验收、
    适用设计材料与相关当前事实页。
  - 均覆盖本轮范围检查正确性、验收覆盖、测试质量、code smell、架构合理性及非必要复杂度。
  - 不安排分工，不按文件、模块或领域拆分，不共享其他审查者结论。
- `partition` 时 owner 按 design 已有切片或本步切开的范围派工，每人只审自己那片；
  仍不共享其他审查者结论。
- 覆盖冻结值与模型：
  - 调用可带 `--review-strategy` / `--code-review-model` 覆盖冻结值，派工前运行 `delivery roster` 写入。
  - roster.models 含 `code-review` 时写入该值，按口语描述现场解析；
    可多个模型，可分给本轮多名审查者。没有则不提。
  - ❌ 不得写入其他 intent 的模型。
- 增量新一轮还必须带上轮已采纳项与未解决项；不能只看新 diff 假装旧问题消失。
  - finish 集成增量轮（1 人）只使用该已汇总清单，
    不得把上轮多份独立报告交给本轮 reviewer 自行合并。
- 已记载的当前行为以事实页为回归基线：与本次目标无关的行为变化按问题报告。
- 每份任务均包含 `repository-contract.md` 的体积与 ignore 条款；涉及文档时另含 `doc-structure.md`。
  - 先核对 `.mdf/modules.yaml`；命中 module `ignore` 的文件报告排除依据，不提出长度或拆分问题。
  - 核对本轮触及的源代码与测试源代码单文件最多 1000 行；超限必须拆分，每个结果最多 700 行。
  - 对触及 package 统计全部直属源文件，实现与测试分别最多 50；超限按设计职责拆分，各结果每类最多 35。
  - 对超限文件、行或文档结构，按修改前内容逐个核对拆分结果不超过对应硬限制的 70%。
  - 文件拆分按职责、依赖与适用设计模式审代码，按角色、主题、读者与导航审文档。
    不得把 `part1`、`part2` 或仅改名的机械切分验收为通过。
  - 合理设计可迁移入口；不得仅因入口改变或未在原位置保留 facade、re-export、转发壳而提出问题。
    核对设计依据、明确的对外契约，以及调用方、测试、文档和链接是否同步更新。
- 📌 主 Agent 在全部审查结果返回前不修改审查对象；subagent 只读审查，不修改文件或提交。

报告内容（进行中 / 分报告）：

- 每份报告均声明审查种类（首轮 | 增量）、派发所用 tip（base / 左端点 /
  review_head）、已完成的审查范围及未完成项；无未完成项时明确写无。
- 增量轮次须有上轮问题复核表，逐项写明仍解决 / 复开 / 不适用。
- 发现问题时列出问题位置、触发条件、影响与证据；无问题时明确说明未发现问题。
- 体积复核列出未排除的触及代码文件实测行数；发生超限拆分时，列出原大小、硬限制与各结果大小。
  - 文件与 package 拆分另须说明边界依据、各结果职责、主题及依赖关系；只满足数字上限仍是未解决问题。
  - package 复核列出原实现/测试文件数、各结果两类计数与 ignore 依据，子 package 独立计数。
  - 入口迁移列出新入口及调用、导出和引用更新的验证结果，不把保留旧 facade 作为固定验收条件。
  - 未发生超限拆分时明确写无；缺少实测或拆分证据即未完成项，不能验收为完整报告。

报告验收：

- 主 Agent 核对每份报告与派发的左端点、review_head 和本轮范围一致，且无未完成项，
  才验收为完整报告。
- 范围声明缺失、端点不一致或存在未完成项时，要求补齐或重新独立审查；无法补齐则停止。
- 不足本轮应派人数、启动失败、结果缺失或未覆盖本轮范围时，补齐独立审查；
  无法补齐则停止，不记录通过。
- 续办只复用同一左端点与 review_head 的完整报告；本轮未凑齐应派份数时不得进入修复或收口。
  - 增量新一轮不复用上轮分报告去覆盖新 diff；收口终稿另见步骤 4。

### 汇总、修复与复核

步骤 3 由主 Agent 汇总去重，逐项核实，记录采纳或不采纳的依据；以证据裁定，不按票数决定。

可选加速（见 `common.md`「Jev 可选加速」）：

- 时机：汇总去重后；tool 可用时。
- 每项：`score`（0=不采纳 / 1=建议修 / 2=必须修）。
- 收口：`choice`（`continue_fix` / `ready_to_close` / `need_human`）。
- state：问题摘要与证据指针。
- 采信后仍须主 Agent 核实依据并写入记录；未采信走原汇总。
- ❌ 不按 Jev 票数代替证据。

- 修复权限：
  - 允许自主修复实现，或依据已确认目标/设计纠正、补充、删除错误或重复测试，记录依据。
  - ❌ 不得削弱验收或验证门槛；目标/契约变更须用户确认。
- adhoc 按 smart 选题核对覆盖；其余核对 design policy `suites` 或 `suites.json` 覆盖本轮功能块。
  缺漏按问题提出。
- 审查测试时核对 `delivery-contract.md`「失败语义」：
  - 无运行时 skip、提前返回或 xfail。
  - 入口配置能让 warning、skip 与空选择非零退出。
  - 豁免已记录且经用户确认。
  - 混合依赖的 test case 按问题提出，可依既定目标自主拆分，不得改成 skip。
- 更好的架构可以建议，超出目标不直接实施。
- 修复后由主 Agent 复核问题是否解决及是否引入回归，不强制再次启动审查 subagent。
  - 本步触及的代码与超限拆分按步骤 2 的体积规则实测，将结果补入复核记录。
- 同一范围内的修复、复核及 smart 循环留在步骤 3–4，不重新执行本轮多人审查。
  - 这是修复窗。报告已齐时不提前跑 verify branch、不开增量新一轮。
- 需要用户决定、外部条件或无法继续时报告阻塞，不记录通过的结果。

### 验证与持久证据

步骤 4：按是否改动实现、测试或验证配置决定是否跑 smart；裁定本 intent 可收口时洗成终稿。

- 本步不跑 verify branch（留给主链下一 intent）；也不写 `gates/code-review.json`。
- 本轮改动了实现/测试/验证配置：跑 `$mdf verify --scope smart`；失败回 3 修。
  - 未改实现/测试/验证配置：跳过 smart。
- close-out 集成后的增量审查仍按下方「close-out 核对」；branch 验证证据由主链
  `verification-report.json` 负责，不在本步伪造。
- ❌ 不能用仅检查文档结构的全量 validation 代替业务验证。
- 非 quick 用例在 converge 之后失败且本轮触及：
  - 必须尝试补一条 quick 复现用例。
  - 结果写入终稿「quick 复现」字段。

进行中草稿（未裁定收口前）可按轮保留 tip，便于续办；每轮操作内容包括：

- round、审查种类（首轮 | 增量）、base_commit、左端点、review_head。
- 本轮应派人数份独立审查及其身份、本轮新发现、上轮问题复核表。
- 逐项裁定、修复与复核、本轮修复终点 tip。
- smart（已跑 <命令/路径> / 未改实现、测试或验证配置跳过）。
- quick 复现（已补 <用例位置> / 未补 <原因> / 无非 quick 失败）、未解决项。

裁定收口（无有效未解决问题，且若本轮改过实现、测试或验证配置则 smart 已通过）时：

1. 合并各轮/各份进行中材料，覆盖写入一份
   `changes/unreleased/<slug>/code-review.md` **终稿**（**report**，非 gate）。
2. 终稿须含：结论（声称通过）、已采纳与未解决清单（未解决须为空）、各轮要点与
   裁定摘要、smart、quick 复现；路径与证据指针用仓库相对路径，不用 commit hash。
3. rule 内容指纹须明确标注，不属于 commit hash；终稿保留该证据。
   ❌ 终稿不得出现任何 commit hash（含 base_commit / review_head / final_head /
   左端点 tip、完整或缩写 SHA）。
4. 进行中带 tip 的段落不得留在终稿；分报告已合并后不再作为核对对象。
5. 提交终稿，将 `objectives.md` 的 code-review 项改为 `[x]` 并提交。
6. ❌ 报告未齐或仍在修复窗时不得洗稿、不得勾选。

- ❌ 不运行 `delivery record --stage code-review`；不以 gate 文件为进度。
- 语义审查由 Agent 负责；CLI 不推理各份结论。
- 首轮未写清已采纳/未解决问题清单时，第二轮不得增量，停止并要求补记录。
- 主链随后的 verify branch 若为修绿改了代码：不强制回到本 intent；由 verify 自行架构审视。
- 勾选后又改实现/测试/验证配置：终稿作废，重新进入本 intent（增量或首轮），再出新终稿。

close-out 核对：

- 终稿存在且声称通过；已采纳/未解决清单齐全（未解决为空）。
- 不使实现审查过期、也不强制重开审查的改动（事实仍须另审）：
  - 记录文件自身、纯事实、收口文档。
  - close-out 集成引入的非本交付 `docs/` 改动。
  - 主链 verify branch 为修绿所做的改动（已在 verify 内自行架构审视）。
- close-out 集成 develop/master 产生新提交后：
  - 仅非本交付 `docs/` 增量不新开审查；按 close-out 契约追加跳过说明。
  - 其他集成增量一律作为增量新一轮从 1 开始，左端点为集成前 HEAD（当场记录）。
    - 以集成后的 HEAD 重做 1 份本轮范围审查与按需 smart；不复用集成前终稿当增量差。
    - 本轮完成后再次洗成无 commit 终稿并勾选。
  - 无有效上轮（无终稿或清单残缺）时按首轮从交付起点审到集成后 HEAD，人数仍为
    roster.reviewers。
- 记录或提交失败时保留现场并报告；不把阶段提交视为审查通过。
