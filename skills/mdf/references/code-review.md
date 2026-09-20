# Code Review

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 已齐审查且修复续办 ────→ 3 Repair
                 ├──── 已齐审查且无新改动 ────→ [结束]
                 ├──── 失败或缺失 ────────────→ [停止并报告]
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
                 ├──── 缺 suites.json ──────→ 1 Check
                 ├──── 重验失败且可修复 ────→ 3 Repair
                 ├──── 通过 ────────────────→ [结束]
                 └──── 其他失败或缺失 ──────→ [停止并报告]
```

## 工作流（唯一执行契约）

读取 `references/common.md`；feature 另读 `references/delivery-contract.md`；
涉及 PRP 或 Bug 时读取 `references/object-contract.md`。
CLI 使用 `python3 "$MDF_ROOT/scripts/mdf.py"`。
独立调用只推进当前 intent；deliver 内部委托时完成后返回调用方，由其选择下一阶段。
finish 内部委托时完成后返回 finish，继续事实审阅与收口。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check | 约束 | 核对范围、前置条件及续办证据 | 基线、报告、检查结果 | 修复续办 3；无新则结束；否则 2 | 停止并报告 |
| 2 | Review | Subagent | 按 roster.reviewers（默认 3）启动独立 subagent 覆盖本轮 | N 份完整审查 | 3 | 停止并报告 |
| 3 | Repair | 约束 | 主 Agent 汇总裁定、修复并复核 | 发现、裁定、修复依据 | 4 | 保留现场并报告 |
| 4 | Record | 脚本 | 按需重验、保存证据并提交 | 审查记录、验证、提交 | 结束 | 缺 suite 则 1；可修则 3；否则停 |

## 术语与数据结构

### 范围与前置条件

步骤 1 支持 feature、bugfix、hotfix、release；cwd 为 qa/dev 时切回 owner。
先确认目标仓库 ready，读取已有审查记录，识别相关未提交改动并按公共规则提交。
审查人数取冻结 roster.reviewers：有 `delivery.json` 时用 `delivery status`，
否则读 `branch.<owner>.mdf-roster`；未冻结则停止。
本轮应派人数默认同 roster.reviewers；finish 集成产生的不可跳过增量新一轮为 1，
不改冻结 roster。无有效上轮记录而走首轮时仍用 roster.reviewers。
审查记录写在 `changes/unreleased/<slug>/code-review.md`：feature 用 delivery.json
的 slug，bugfix 用 Bug ID 的 kebab-case，release/hotfix 用该分支的稳定 SemVer，
不用 slugify。验证 JSON 为同目录 `code-review.verification.json`。无该 Markdown
视为无记录。不在 `docs/context/research/` 保存审查报告。

无记录时走首轮：首次审查才固定当前 HEAD 为 review_head。
已有同范围修复续办保留原 review_head，不覆盖原报告。
本轮应派人数份报告齐全、基线一致且本次仅为已记录问题的修复续办时，核对前置条件后
直接进入 3。
报告齐全、基线一致、无待修问题，且 final_head 到 HEAD 没有新的交付改动时，核对后结束，
不进入 2。记录文件、纯事实、收口文档、以及非本交付 `docs/` 不是新的交付改动。
首轮未齐时进入 2 补齐；若首轮尚未完成但出现新交付改动，重新固定 review_head，
仍按首轮从交付起点审查到新 review_head。
同一分支已有完整上轮记录（该轮应派份数的报告、final_head、已采纳与未解决问题清单）且
出现新的交付改动时，进入增量新一轮：左端点为上轮 final_head，重新固定
review_head 为当前 HEAD，进入 2。不得从 start_commit 重扫已审区间。
上轮记录残缺（缺份数、缺 final_head、缺问题清单、或 final_head 不是当前 HEAD
的祖先）时不得假装增量，停止并要求补记录。无记录走首轮。范围无法判定时停止询问。
不得把未提交改动遗漏在审查范围外；存在无关改动且无法隔离时停止。

| 分支 | 固定基线 |
| --- | --- |
| feature | delivery.json 的 start_commit |
| bugfix、hotfix | start 保存的 `branch.<完整分支名>.mdf-start-commit` |
| release | 上一正式发布版本的 master commit/tag，解析为完整 commit hash |

bugfix/hotfix 用 `git config --local --get "branch.<完整分支名>.mdf-start-commit"` 读取起点。
release 首轮依据正式发布记录确认上一版本，核对其 `v<version>` tag 指向的 commit 位于 master 历史。
不取 master 合回 develop 的合并提交，也不使用移动的 master/develop HEAD 代替发布基线。
首次发布没有上一版本时，须用户明确确认初始基线；基线缺失、歧义或对象不可解析时停止询问。
基线必须是当前 HEAD 的祖先。首轮审查两个端点的内容差异
`git diff <base_commit> <review_head>`；增量新一轮审查
`git diff <previous_final_head> <review_head>`。
并读取必要上下文，不能仅按提交标题或文件名审查。release 首轮覆盖上一版本以来
的完整变化，不得仅审 release 分支创建后的改动，也不得因某个 child 已审查而跳过
其代码。后续轮次只覆盖上轮 final_head 以来的增量，仍须复核上轮问题。
步骤 1 仅在新审查或增量新一轮时将本轮左端点与 review_head 写入草稿，明确尚未
通过，再启动审查。
交付起点 base_commit 写入本次审查记录后固定，续办沿用，不重新追随分支或 tag。

feature 保留前置要求：运行 `delivery status` 定位材料，读取 design 与 converge gate，
核对两者的 `fingerprints.design` 一致；收敛记录缺失、损坏或设计不一致时停止。
运行 `delivery check --stage code-review`；通过则按步骤 1 的报告有效性与续办条件进入 2 或 3。
仅返回 `stale_verification` 且同设计已收敛时，记录过期或失败状态，按相同条件进入 2 或 3，
并在步骤 4 按所需 suite 重验。
其他错误停止，不跳过 converge。bugfix/hotfix/release 不要求 feature 的 design/converge gate；
读取对应 Bug、交付目标、版本材料及适用设计作为审查依据，不为形式创建 feature 材料。

分层仓库的 bugfix 在本步骤另核对 `changes/unreleased/<slug>/suites.json`
（`{"suites":["<已有 suite 名>"]}`）：文件缺失时，按 Bug 与适用设计从 manifest
已有交付 suite 中选定 ≥1 个写入并提交；没有合适的已有 suite 时停止，询问用户
是否新建，确认后先在 manifest `verification.suites` 新增该 key 再关联。不得只关联 quick/full，
不得未经确认新建。未分层不要求该文件。

### 独立审查

主 Agent 向每个审查 subagent 派发任务时，必须以以下文字作为提示词 opening，
随后提供本次审查上下文及现有执行与输出约束：

> 以最严苛的白盒测试专家视角审查实现代码和测试用例，主动挑战实现逻辑与测试的充分性，
> 寻找隐藏缺陷和覆盖盲区。以证据核实逻辑正确性与测试有效性，不因测试通过就认定实现正确。

步骤 2 按本轮应派人数启动独立 subagent。默认为 roster.reviewers（默认 3）；
finish 集成增量轮为 1。
`review_strategy` 默认 `replicate`：各审查者收到相同的交付
base_commit、本轮左端点、
review_head、工作目录、目标、验收、适用设计材料与相关当前事实页，均覆盖本轮
范围检查正确性、验收覆盖、测试质量、code smell、架构合理性及非必要复杂度。
不安排分工，不按文件、模块或领域拆分，不共享其他审查者结论。
`partition` 时 owner 按 design 已有切片或本步切开的范围派工，每人只审自己那片；
仍不共享其他审查者结论。调用可带 `--review-strategy` / `--code-review-model` 覆盖冻结值，
派工前运行 `delivery roster` 写入。roster.models 含 `code-review` 时写入该值；
没有则不提。不得写入其他 intent 的模型。
增量新一轮还必须带上轮已采纳项与未解决项；不能只看新 diff 假装旧问题消失。
finish 集成增量轮（1 人）只使用该已汇总清单，不得把上轮多份独立报告交给本轮
reviewer 自行合并。
已记载的当前行为以事实页为回归基线：与本次目标无关的行为变化按问题报告。
主 Agent 在全部审查结果返回前不修改审查对象；subagent 只读审查，不修改文件或提交。
每份报告均声明审查种类（首轮 | 增量）、交付 base_commit、本轮左端点、review_head、
已完成的审查范围及未完成项；无未完成项时明确写无。
增量轮次须有上轮问题复核表，逐项写明仍解决 / 复开 / 不适用。
发现问题时列出问题位置、触发条件、影响与证据；无问题时明确说明未发现问题。
主 Agent 核对每份报告与派发的左端点、review_head 和本轮范围一致，且无未完成项，
才验收为完整报告。
范围声明缺失、端点不一致或存在未完成项时，要求补齐或重新独立审查；无法补齐则停止。
不足本轮应派人数、启动失败、结果缺失或未覆盖本轮范围时，补齐独立审查；无法补齐则停止，
不记录通过。
续办只复用同一左端点与 review_head 的完整报告；本轮未凑齐应派份数时不得进入修复或
记录完成。增量新一轮不复用上轮报告去覆盖新 diff。

### 汇总、修复与复核

步骤 3 由主 Agent 汇总去重，逐项核实，记录采纳或不采纳的依据；以证据裁定，不按票数决定。
允许自主修复实现，或依据已确认目标/设计纠正、补充、删除错误或重复测试，记录依据。
不得削弱验收或验证门槛；目标/契约变更须用户确认。更好的架构可以建议，超出目标不直接实施。
修复后由主 Agent 复核问题是否解决及是否引入回归，不强制再次启动审查 subagent。
同一范围内的修复、复核及重验循环留在步骤 3–4，不重新执行本轮多人审查。
需要用户决定、外部条件或无法继续时报告阻塞，不记录通过的结果。

### 验证与持久证据

步骤 4：feature 先运行 `delivery check --stage code-review`；除 `stale_verification` 外的错误均停止。
finish 本次集成产生新提交且增量不可跳过、返回 `stale_verification` 或本轮改动实现、
测试、验证配置时，运行 `delivery verify` 按所需 suite 重验。仅非本交付 `docs/` 的集成
不强制重验。仅检查通过且上述强制重验条件均不成立时，沿用有效全绿证据。
bugfix/hotfix/release 运行 `project-verify run --repo "$REPO_ROOT"`，
脚本按当前分支执行所需 suite（release/hotfix 为全局 full；bugfix 为全局
quick 加已关联交付 suite），逐项记录命令、退出状态与 `suites`，
输出并保存同目录 `code-review.verification.json`；失败保留失败证据。
分层后 bugfix 返回 `missing_delivery_suite`（缺 `suites.json`）时回步骤 1 补关联；
返回 `unknown_suite`（引用尚未写入 manifest 的名称）时停止，询问用户是否新建。
证据只覆盖 quick 视为过期。finish 使用 `project-verify check --repo "$REPO_ROOT"`
核对输入指纹、suite 与全绿结果。
不能用仅检查文档结构的 full validation 代替业务验证。
重验失败且可在既定权限内修复时返回 3，由主 Agent 修复、复核并重验。
非 quick 用例在 converge 之后（或 bugfix/release/hotfix 等价门禁之后）失败时，
必须尝试补一条 quick 复现用例，并在本轮记录的「quick 复现」字段写明结果。

四种分支均在 `changes/unreleased/<slug>/code-review.md` 按轮追加审查记录，
每轮包含 round、审查种类（首轮 | 增量）、固定的交付 base_commit、本轮左端点
（首轮 = base_commit，增量 = 上轮 final_head）、本轮 review_head、本轮应派人数份独立审查
及其身份、本轮新发现、上轮问题复核表、逐项裁定、修复与复核、本轮结束后的
最终 final_head、验证命令与结果（含 `suites`）、quick 复现（已补 <用例位置>
/ 未补 <原因> / 无非 quick 失败）、未解决项。先提交修复，再固定 final_head 并
提交本轮记录。
无有效未解决问题且验证全绿才可记录完成。feature 另运行
`delivery record --stage code-review --summary <审查、裁定、修复与验证依据>` 并提交 gate。
非 feature 以该审查记录为证据，不伪造 feature gate；语义审查由 Agent 负责，CLI 不推理各份结论。
首轮未写清已采纳/未解决问题清单时，第二轮不得增量，停止并要求补记录。

finish 核对记录中的基线、各轮应派份数的审查结果、最终复核及验证均完整，并检查 final_head 到当前 HEAD
是否有实现、测试、验证配置或本交付目标变化；final_head 必须存在且为当前 HEAD 的祖先。
记录文件自身、纯事实、收口文档、以及 finish 集成引入的非本交付 `docs/` 改动不使实现审查过期，
也不强制重验；事实仍须另审。实现或本交付目标变化后不得沿用通过结论：同次修复续办回到 3；
新交付改动作为增量新一轮从 1 开始。finish 集成 develop/master 产生新提交后，仅非本交付
`docs/` 增量不新开审查、不重验；按 finish 契约追加跳过说明，不把集成当修复续办。其他增量
一律作为增量新一轮从 1 开始，左端点为集成前 final_head，以集成后的 HEAD 重做
1 份本轮范围审查与当前交付所需 suite。不复用集成前报告。无有效上轮记录时
按首轮从交付起点审到集成后 HEAD，不得跳过，人数仍为 roster.reviewers。
feature 还须通过 CLI 指纹检查。
记录或提交失败时保留现场并报告；不把阶段提交视为审查通过。
