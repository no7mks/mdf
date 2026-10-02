# 交付契约

由 deliver 与各交付 intent（含 verify、fact、close-out）读取。
`$mdf finish` 同义 close-out。`$mdf integrate` 只读「补覆盖」。
规则持续适用，不是依次执行的阶段。
## 身份与材料

一个 feature 对应一个依赖满足的 active ready PRP。

- start 经 clarify（bugfix/hotfix 可精简）写入 `objectives.md`。
  并冻结 `needs_design: yes|no`（objectives 与 `delivery.json`）。
- feature 的 objectives 引用 PRP，避免复制另一个需求来源。
- release 的 objectives 写已选定工作线、本版收口范围、预发布工作、联调、
  `has_dev`、非目标与可验证验收，不引用单个 PRP。
  - 工作线只保留开分支前选定的一条，不罗列未选路径。
  - 冻结 `has_dev: yes|no`：本 release 分支是否包含预发布/开发代码改动。
    - `no`：start 写入时即将 owner 开发、converge（及无事务时的预发布工作）勾为
      `[x]`；不跑这些 intent。
    - `yes`：保留未勾，走 owner 开发 → converge。
  - checklist **必须含** integrate 项；不联调由 start 写入时勾 `[x]`；同/跨
    worktree 由 `$mdf integrate` 收口自勾。deliver/next **只读该勾选**。
  - 该分支不得实施新 PRP。工作线三选一，只写选定的一条。
  - 不联调不执行 integrate intent。同 worktree 执行 integrate，不打开消息通道。
  - 跨 worktree 切到 worktree 后先开通道。只改本仓，不得改、操作、启动或终止对端。
  - 两种联调都强制 Goal。Goal 完成前，用户没让你停，永远不许停下来。
  - 两端验收且确认不再改代码后才允许 code-review（且 integrate 项须已 `[x]`）。
- start 后四种工作分支均须有 `objectives.md`，含 `[ ]` / `[x]` 大步骤 checklist。
  - bugfix / hotfix：roster `0,0` 也由 start 写入；roster ≥1 可由 design 修订。
  - hotfix 始终在 `changes/unreleased/<semver>/objectives.md` 记录已确认的热修复范围。

身份字段：

- slug 取自 PRP 文件名，start 固定使用，不随标题修改。
- delivery.json 记录 proposal/bug、slug、branch、start_commit、`needs_design`。
- release 的 `has_dev` 只冻结在 objectives（与 checklist 跳过预勾一致），不另写入
  delivery.json。
- 起点是创建分支前基线的完整 commit hash，不用移动的 develop/master 代替。

材料位置：

- 开发材料自 start 起位于 `changes/unreleased/<slug>/`：
  - objectives.md、delivery.json、可选 gates/（配置快照）、code-review.md；
    `needs_design: yes` 时另有 design.md。
  - close-out 在同一目录补齐 CHANGE.md，不搬迁；发布后随目录进入
    `changes/<version>/<slug>/`。
- release 材料位于 `changes/unreleased/<semver>/`：start 写入 objectives.md 与 delivery.json。
- 代码、测试、fixture 留在项目原位置，大日志不要求提交。

路径写法：

- objectives/design 是受管可搬迁 Markdown。
- 仓内 Markdown 本地链接只相对当前文件（`./`、`../` 或同级文件名）；前导 `/` 是站点根，不是仓根。
- 搬迁时 CLI 改写仍有效的相对路径。
- delivery.json 与可选 gate 快照内路径一律仓库相对。
- fingerprint 规范化用仓库相对或 `@delivery/`，不是第二种 href 写法。
## 阶段与执行责任

四种 kind **共用**主线。不按 branch kind 另写交付状态机。
并行形态与是否 design 由默认 roster 与 `needs_design` 决定；
**有无开发阶段**看 objectives checklist（及 release 的 `has_dev`）。
**不**由 roster `0,0` 推导出必须空转的 owner 开发 / converge。

主线步骤：

1. start
2. release：integrate（checklist 项；不联调已由 start 勾掉则跳过 intent）
3. 可选 design
4. write-tests / implement，或 owner 开发（无对应未勾项则跳过）
5. converge（无对应未勾项则跳过）
6. code-review
7. verify branch
8. fact audit（必要时 fact update 后重审）
9. close-out

- **是否 design**：start clarify 冻结 `needs_design`；deliver/next 只读该字段。
  - `roster ≥1` 必须 `needs_design: yes`；选 no 则须收成 `0,0`。
- **进度**：唯一账本是 `objectives.md` 步骤 checklist；各 intent 成功后**自勾**。
  - deliver / next 只读勾选与依赖决定下一 intent，**不**读 stage gate、**不**对 report 做过期审判。
  - roster `0,0` 只表示无 qa/dev 角色；不自动要求 owner 开发或 converge。
- **converge**：仅当 checklist 的 converge 项仍为 `[ ]` 时进入；核对前置已勾，跑
  **verify smart**，修到达成后自勾。
  - ❌ converge 的「验」不是 verify branch。
- **verify branch / code-review / fact**：独立 intent；落盘均为 **report**（非 gate）。
  - verify 默认 suite：feature/bugfix/hotfix → smoke；release → release；失败现场修到绿。
  - fact：verify branch 之后、close-out 之前 audit；未通过则 update 后重审。默认 scope=`branch`。
- **close-out**（`$mdf finish` 同义）：材料与 Gitflow 收口。
  - 只查 report **交没交**（有文件且声称通过）；不复验报告对不对、不做 commit 对齐审判。
  - 不内嵌、不委托 verify（branch / smart / named）；不内嵌 fact。
    bug close 不算 verify 族，release/hotfix 收口步骤可委托。
  - `release-closeout` 只复用可复用的 `verification-report.json`，永不执行验证命令。
  - 把目标主线合入交付分支前可建议 squash（见「可选历史整理」）；非强制。
- 开发迭代只用 `$mdf verify --scope smart`；branch 只用于交付验收。
- release/hotfix 可修已确认 open Bug，标 `fixed`；不另开 bugfix。
- 独立 `$mdf fix` / `$mdf bug close` 不走交付主线，也不由 deliver 内部委托。
- code-review 份数取冻结的 roster.reviewers；close-out 增量新一轮为 1。
### 触发与协调

- 用户手动触发主线 intent，或显式调用 next 委托下一阶段。
- 显式 deliver 按 `references/deliver.md` 串联剩余真实 intent 到 close-out。
  - 可并行阶段按 roster 分别委托 subagent。
  - `--auto-pilot` 由主 Agent 自裁定，仅在 Gitflow 收口前确认。
  - `--yolo` 跳过该确认。
- design 的 Baseline 与 converge 由各 intent 启动恰好 1 个 owner subagent，不计入 roster。
- deliver 步骤 4 只覆盖可并行的 qa/dev。
- 不新增独立 Owner 调度服务或统一状态协议。
- 当前执行者承担该阶段的协调与语义审查。
### worktree 与 roster

- start 始终从基线在仓库同级 `<repo-name>-worktrees/<worktree-name>` 建立交付 worktree，
  路径等于分支名；不在当前目录开分支，不 fetch、不 push。
  - 有 origin 时基线的远程提交必须已在本地；本地可以更新。
- roster 在 start 开分支前展示 member、strategy 与 models 并经确认后冻结。
  - 写入 `delivery.json`（有交付材料时）与 `branch.<owner>.mdf-roster`。
  - 字段为 `qa`、`dev`、`reviewers`，以及 `qa_strategy`、`dev_strategy`、`review_strategy`；
    可选 `models`。
- owner 恒为 1。

| kind | 默认 named roster |
| --- | --- |
| feature | `min-tdd`（`1,1,2` + best-of-n） |
| release | `solo`，但 reviewers 为 3、`review_strategy` 为 `partition` |
| bugfix、hotfix | `solo`（`0,0,1`） |

- 点名 `--roster` 时不叠加该 release 默认。
- 也可用 `competing-pair`（`2,2,3` 竞争）或 `coop-pair`（`2,2,3` 分工）。
- 四种 kind 都可改人数或改名。
- qa 与 dev 只能同时为 0 或都 ≥1；一侧为 0 另一侧 ≥1 时把 0 抬成 1 再冻结。
- `0,0` 时测试与实现都在 owner 上做。
- `≥1` 时 start 按人数建立 `qa/<owner>`、`dev/<owner>`，第 2 路起为 `qa/2/<owner>`、`dev/2/<owner>`。
### 底座、执行者与策略

- design 只在 owner 提交共用代码底座；两路不得各自再写底座。
- design 不创建角色 worktree。
- Clarify 由当前 Agent 在主会话完成；Baseline 由该 intent 启动恰好 1 个 owner subagent 写入。
- converge 由该 intent 启动恰好 1 个 owner subagent 执行 roster-join、验证与记录；测试修改批准回主会话。
- 均不可配人数；无法启动则停止，不降级由当前 Agent 代做。
- write-tests 与 implement 在对应角色树上执行，入口先 no-ff merge owner；
  `0,0` 时在 owner 上编写测试与实现。
- qa 与 dev 互不传入路径。同侧 ≥2 时并行互不知情。

| 侧 | 策略 | 规则 |
| --- | --- | --- |
| qa/dev | `best-of-n`（默认） | converge 选 base 并只合 winner，集成后在 owner 吸收其余优点 |
| qa/dev | `partition` | design 写明各 index 切片，converge 按 index 全部合入，冲突视为分工重叠并停止 |
| review | `replicate`（默认） | 每人覆盖同一份本轮范围 |
| review | `partition` | 按切片审查 |

- 各路并行产出在合入前按分支核验；同路径冲突时保留先合入的版本。
  - qa 为 `partition` 且 ≥2 时：roster-join 合完全部 qa 后，
    可写 `gates/roster-join.json` 测试 fingerprint 快照。
  - 该文件是配置/辅助，**不是**进度 gate。
- review 时 owner 仍汇总裁定，不按票数。
### intent 参数与 models

- `$mdf start`、`$mdf deliver` 可带 `--roster <name>`，只在尚未 start 时展开；
  已 start 后再带 `--roster` 停止。
- `$mdf start`、`$mdf design`、`$mdf deliver`、`$mdf code-review` 可带下列参数：
  - `--qa-strategy`、`--dev-strategy`、`--review-strategy`。
  - `--write-tests-model`、`--implement-model`、`--code-review-model`。
- 这些是 intent 参数，不是独立 intent。start 冻结；之后由 Agent 调用 `delivery roster` 写入。
- qa/dev strategy 在 design **完成后**锁定（看 objectives 勾选，不靠 stage gate）。
- review_strategy 与 `models.code-review` 可在 code-review 覆盖。
- deliver 把 strategy / models 转交给 start、design、code-review；`--roster` 只转交 start。
- 未知 `--` token 停止询问。

models 取值：

- 每个 `--*-model` 取随后一个 token（口语整句，可含空格）；未带的 intent 不写、不问、不提。
- `models` 按 intent 可选，键只允许 `write-tests`、`implement`、`code-review`。
- 值为一句口语描述：可点名一个或多个模型，不要求官方 id 或固定分隔格式。
- Agent 分派某 intent 的 subagent 时只读取并写入该键，现场解析并选用。
  - 该路有多名执行者时可把多个模型分给他们。
  - 没有则不提模型或 effort。
  - 不得把其他 intent 的模型写入本路任务。
- 策略字段的 JSON 键为下划线形式。

Git 约束：

- 本地工作分支不推送。
- 禁止 rebase，异名分支使用 no-ff；合并冲突保留现场。
## 进度与 Report

**进度唯一账本**：`objectives.md` 步骤 checklist。各 intent 成功收尾必须自勾对应项并提交。

- deliver / next / 人工续办：只读勾选决定下一 intent。
- write-tests 写完可编译或可加载执行的测试即完成，**不要求全绿**；完成后自勾 objectives。
- ❌ 不以 `gates/<stage>.json`、`verification-report.json`、fact 确认、`code-review.md` 当阶段通行证。
- ❌ 不对 report 做「相对 HEAD / 相对上游 intent」的过期 gatekeeping。

**Report**（证明做过与结果，供核对「交没交」）：

| Report | 典型路径 | 谁写 |
| --- | --- | --- |
| code-review | `…/code-review.md` 无 commit 终稿 | code-review |
| verify branch | `…/verification-report.json`（及可选 `verification-report.md`） | verify branch |
| fact | 材料目录内 confirmation / 会话确认记录 | fact audit（经 update 委托时同） |
| 测试框架报告 | `.mdf/reports/` 等 | verify |

close-out 只查上表是否已交且声称通过；不复验对不对。
### CLI 确定性辅助（非进度）

`delivery status/check/record/roster-join/roster` 仍可执行。

- `record --stage design` 可写入 **design policy 配置快照**
  （protected_paths / suites）。
  - 语义是配置/report，**不是**进度 gate。
- `record/check` 其他 stage、以及 `gates/*.json` fingerprint：
  **禁止**当作进度或验收关口。
  - 并行 e2e/旧脚本可能仍调用。
  - Agent 主链不得用其选型或卡 close-out。

测试门槛与所需 suite：

- 设计 policy 的 protected_paths 覆盖所有测试、fixture、快照和工具配置，包括 named suite 的路径。
  - modules.yaml 的分套件入口始终属于测试门槛。
  - 路径可以是仓库相对文件、目录或 glob。
- design policy 必须另含 `suites`：本交付改动涉及的全部功能块的 named suite 名。
  - 非空列表，不得使用 lint/build/quick/smoke/release/full。
- 点名执行 test case 或 test 仅用于定位，不替代所需 suite 通过。
- `$mdf verify` / 验证 report 必须写出 Core 实际跑过的 `suites`。

补验（仅在**该** intent 内）：

- 开发中与 converge 只跑 module **smart**。
- **verify branch**：无论成败均写入 `verification-report.json`（不含 commit）；未绿可修则
  先落盘再修、重跑，直至绿后勾选；未绿轮不写通过用 `verification-report.md`、不勾选。
- 只改事实文档或 module ignore：不因「报告对齐」要求机械重跑 branch
  （close-out 也不做 commit 对齐审判）。
- fact / code-review / verify 均无 delivery stage gate。
### 测试层级与分类

- 层级：test 是含若干断言的最小测试项，通常为函数；test case 是服务于同一目标的
  一组 test，通常为类或文件；suite 是 test case 的集合。suite 成员粒度是
  test case，归属写在代码里（marker、目录等），文档只写选择规则，不逐条列举。
- kind 按测试对象划分：UT 测内部单元；IT 测产品真实开放的接口（lib 的函数、
  服务的 API 等），一般不用 mock；E2E 走用户最终入口（浏览器、模拟器、命令行
  调用、使用 lib 的 demo-app）。PT 是生成输入并断言不变式的手法，可用于任一层级。
- 依赖按是否 hermetic 划分：测试进程能自行拉起全部依赖、不需要预先存在的环境、
  凭据或网络即为 hermetic；依赖第三方资源或真实兄弟产品（如联调对端）即为
  external。第三方资源不含待测产品与兄弟产品；mock 掉兄弟产品后才算 hermetic。
### 失败语义

五个入口出现以下任一情况都是失败：

- 非零退出。
- warning、notice、deprecated。
- skip。
- xfail 或 xpass，以及 suite 未选中任何 test。

运行时约束：

- test case 是否属于本次 target 由 suite 的成员选择规则在收集阶段决定。
  - ❌ 不得在运行时按环境变量、配置或资源是否可用去 skip 或提前返回。
- external 资源未就绪即失败。
- 已知缺陷登记为 Bug 并把对应 test 移出 suite，不用 xfail 保留。

test case 内有 test 依赖当前 suite 不具备的条件时，按依赖
拆成多个 test case 分别归入合适的 suite；不得整体移出，也不得保留 skip。

Core 判定退出码与测试报告（见下节）。

- 报告无法体现的 warning、notice、deprecated，项目须让入口命令或测试运行器非零退出，
  并把配置写进 `docs/system/testing/`；code-review 核对该配置。
- 第三方依赖产生、本项目无法修复的 warning 或 deprecated 只可精确豁免。
  - 写明类别、来源模块与理由，记在 `docs/system/testing/`，新增或放宽须用户确认。
### 测试失败工作流

converge（smart）与 verify branch **共用**：

1. 测试运行必须有框架自带报告文件（JUnit 等），禁止靠 tee/tail 冒充报告。
2. fail 后先复测**单用例**。
3. 修一个用例 → 复测该单用例。
4. 有 side effect 的 flaky 例外（须记录依据）。
5. 相关单用例都绿后，才继续该轮 verify（smart 或 branch）。
### 测试报告

每次运行 suite（含 named suite）都必须产出 JUnit XML 报告。

- Core 为每次运行新建 `.mdf/reports/<时间戳>-<suite>/`，以环境变量 `MDF_REPORT_DIR` 传给入口命令，
  命令把 XML 写进该目录；lint 与 build 也各有运行目录。
- 每个运行目录都保存该命令完整的 `stdout.log` 与 `stderr.log`。
- `.mdf/reports/` 由 Core 自带 `.gitignore` 忽略，7 天前的条目自动清理，见 `common.md`「日志与报告」。
- test case 取 `<testcase>` 的 `classname`，缺失时取所在 `<testsuite>` 的 `name`；
  项目须配置运行器使其对应 test case。
- Core 解析后在同目录写 `summary.json`：test case 级的结果与用时，及其下 test 级的
  结果与用时。report 与 code-review 记录报告路径与 test case 级汇总。
- 缺报告、报告无法解析、未含任何 test，或含 failure、error、skipped（含 xfail）时，
  该 suite 失败，即使命令退出码为 0。
- 点名执行 test case 或 test 只用于定位；定位复测仍应尽量落盘框架报告。
  有运行器报告则读报告；否则用 `mdf.py run` 落盘。
### 验证 suite

| suite | 成员 | 预算 | 何时必跑 |
| --- | --- | --- | --- |
| quick | 只含 hermetic 的 UT 与 PT | 30s | 任何改动 / smart |
| smoke | 任意种类，包含 quick 的全部成员 | 300s | feature/bugfix/hotfix 的 verify branch |
| release | 发版所需的 test case，包含 smoke 的全部成员 | 无 | 仅 release 的 verify branch |
| named | 某一功能块的 test case；一 suite 一文档 | 无 | smart 选题，不默认整 suite |

- 验证入口仅 lint/build/quick/smoke/release；其他保留名称不得用作 named suite。
- lint 与 build 同 quick 一样必跑：smart 只跑涉及 module；branch 跑全部 module。
- 每个 **named** suite 在 `docs/system/testing/<name>.md` **独占一页**。

| 交付阶段 | Core 必须通过 | Agent 另须通过 |
| --- | --- | --- |
| 开发中 / converge smart | 涉及 module 的 lint、build、quick | 本分支新增/改动测试；可选 named 选题 |
| verify branch（feature/bugfix/hotfix） | lint、build、quick、smoke | bugfix 另有 `suites.json` 选题记录 |
| verify branch（release） | lint、build、quick、release | — |
| 主链收口前 | verify branch 绿 + fact audit 通过 | 必要时 fact update |
| 只改事实 / ignore | 不机械重跑业务验证 | — |

named suite：命令在 `docs/system/testing/<name>.md` frontmatter；用 `verify --scope named --suites <名>` 执行。
`needs_design: yes` 时 design 列出涉及的 named suite。
bugfix 的 `suites.json` 在 verify branch 前关联已文档化 named suite（≥1）。

补覆盖与 quick 复现：缺覆盖则先补 reproduce；优先放入 quick，其次 smoke。
verify branch 中非 quick 失败时尝试补 quick 复现；结论写入
`changes/unreleased/<slug>/verification-report.md`。code-review 本轮触及的非 quick 失败另在
`code-review.md` 记「quick 复现」字段（各记各的，不互替）。
## 可选历史整理（squash）

close-out 可在**第一次把目标主线合入交付分支**之前建议整理本地历史。
集成方向：feature/bugfix←develop，release/hotfix←master。非强制；用户拒绝则跳过。
`--auto-pilot` / `--yolo` **不得**擅自改写历史。

**职责**：调用方决定是否激活（启发式 + 用户确认）。公开 `$mdf squash` 负责地板、
切段定型、message、确认后执行；可用 `--dry-run` 只产出建议。
### 地板（`reset --soft` 目标）

地板必须是当前 HEAD 的祖先，且不得早于交付地板；区间为地板..HEAD。

- **交付地板**（能允许的最早点；有 converge 时 = converge 起点）：
  - roster ≥1：`git log -1 --format=%H -- changes/unreleased/<slug>/gates/roster-join.json`
    定位该文件的 commit。它须为该文件在本分支首次引入的 commit；角色 worktree 须已清理；不得早于它。
  - roster `0,0` 且 objectives checklist **含**开发完成项（owner 开发，或
    `needs_design: yes` 下的 write-tests / implement；含 start 跳过预勾）：
    - 在 `start_commit..HEAD` 上找**最晚**一次使**该**项变为 `[x]` 的 commit。
    - 命令：`git log -1 -S'[x]' --format=%H -- changes/unreleased/<slug>/objectives.md`。
    - 再人工核对该 diff 确含该勾选；找不到或歧义 → **不可 squash**（失败/缺失）。
  - roster `0,0` 且 checklist **无**上述开发完成项：交付地板 = `start_commit`。
    若其不是 HEAD 祖先，或 `start_commit..HEAD` 为空 → **不可 squash**。
- **他人抬升**：检查 `start_commit..HEAD`。
  - `author` 或 `committer` email ≠ 当前 `git config user.email` 的 commit 为他人提交。
  - 若存在他人提交，地板抬到其中**最新一笔**；保留该笔，只压其后。
  - tip 本身即他人提交 → 不可 squash。
  - roster merge 落在交付地板之前则不进区间，不必再判「是否本人」。

地板 = 历史上较晚者（交付地板与他人抬升结果取更近 tip 的一侧）。  
有 converge 时由 converge 定义地板语义；本小节供 close-out 选用，converge 入口不询问 squash。
### 是否建议（可选启发式）

无硬门槛。调用方先取得 `$mdf squash` dry-run 计划，再用计划中的地板收集信号，
交 Jev/Agent 定型是否展示（`noul` / `choice`）：

- `git rev-list --count <地板>..HEAD` ≥ 5；或
- `git log --oneline <地板>..HEAD` 含 ≥2 条标题匹配 `wip|fixup|tmp|临时`
  （大小写不敏感）。

- 未达信号也可展示 dry-run 建议。
- 用户拒绝或调用方决定不展示 → 跳过执行。
### 手段（只允许 soft reset）

公开 `$mdf squash` 承担地板计算、切段定型、message 与执行（见
`references/squash.md`）。Jev/Agent 在 squash 内定型几段与切法
（`noul` / `choice` / `run`），**不写** commit message；主 Agent 撰写中文
Conventional Commit（含 Bug 的段保留完整 Bug ID）。调用方的「是否建议」不在本段。

执行：多段 = 1 次 soft reset + N 次按段界树提交；完成后树须与旧 tip 一致，且
`start_commit` 仍为 HEAD 祖先。`--dry-run` 只展示计划、不改写。

❌ 禁止：`git rebase` / `rebase -i`、`git merge --squash`、越过地板、涵盖他人
commit。
❌ 也禁止：已推送分支上改写、审查窗未关时改写、目标主线已合入交付分支后再压。
仅当各段改动文件完全不重叠时，才可偷懒按路径分批；通用流程仍按段界 **tree**。
## 修改与提交权限

调用交付 intent 授权其必要的设计基线、阶段提交和工作分支集成，提交使用中文
Conventional Commit。修复某个 Bug 的提交说明必须含该 Bug 的完整 ID。

- 只暂存当前阶段的必要路径；不得顺带提交无关用户改动。
- 可以主动提交尚未完成的阶段产出，但须准确记录未完成状态。
- 阶段提交不代表 objectives 已勾或 report 已交，不能绕过既有验收与审阅。

各 intent 对测试与验证门槛的权限：

- 首次 write-tests 按既定设计编写测试属于授权：
  - 含把用例归入 quick、smoke 或 design 声明的 named suite。
  - 含在 `docs/system/testing/` 补齐所列 named suite 的文档。
- implement 不自主修改测试；按「补覆盖」补 reproduce 用例除外。
- 按「补覆盖」把 reproduce 用例放入 quick 或 smoke 属于授权，不另走测试修改批准。
- converge 修改测试、预期、fixture、跳过规则或任何验证门槛，需用户明确批准并记录理由。
  - `--auto-pilot` / `--yolo` 由 converge 执行者自裁定并记录。
- code-review 可以依据既定目标和设计自主修复实现与测试；降低验收、改变目标/契约仍需用户确认。
- 非 feature 分支变更 modules.yaml 套件入口或新增 named suite：默认模式需用户确认；
  `--auto-pilot` / `--yolo` 由主 Agent 自裁定并记录依据。
- 架构优化可以建议；超出当前目标不直接实施。
- 修复后在当前 intent 原地重验。

fact update / fact audit 可独立运行；交付主链在 verify branch 之后、close-out 之前委托。
无 fact stage gate；进度靠 objectives 自勾。独立调用不能因此自动进入 close-out 或其他交付阶段。
