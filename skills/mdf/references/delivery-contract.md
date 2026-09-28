# Feature 交付契约

由 deliver、start、design、write-tests、implement、converge、code-review 与 finish
读取。`$mdf integrate` 只读「补覆盖」。规则持续适用，不是依次执行的阶段。

## 身份与材料

一个 feature 对应一个依赖满足的 active ready PRP。

- start 经内部 clarify 确认目标、非目标、约束与可验证验收。
- feature 的 objectives 引用 PRP，避免复制另一个需求来源。
- release 的 objectives 写本版收口范围、预发布工作、是否联调、非目标与可验证验收，不引用单个 PRP。
  - 该分支承担上线前预发布（含跨仓联调），不得实施新 PRP。
  - 必须写明需要或不需要 `$mdf integrate`；需要时切到 worktree 后先开通道。
  - 联调过程强制 Goal，poll 不得停；等待对端按 15、30、45、60 秒输出正在等什么。
  - 联调按模板工作线；双端验收且确认不再改代码后才允许 code-review。
  - fact update 由 finish 前段执行；已有有效结果则不重做。
- start 不为 bugfix/hotfix 写 objectives。
  - bugfix：roster `0,0` 时不需要；roster ≥1 时由 design 的 Baseline 依据 Bug 补写。
  - hotfix 始终在 `changes/unreleased/<semver>/objectives.md` 记录已确认的热修复范围。
    - roster `0,0`：deliver 或开发前的主 Agent 与用户确认后写入并提交。
      `--auto-pilot` 按 Bug 与对话证据自裁定。
    - roster ≥1：由 design 的 Baseline 写入。

身份字段：

- slug 取自 PRP 文件名，start 固定使用，不随标题修改。
- delivery.json 记录 proposal、slug、branch、start_commit。
- 起点是创建 feature 前 develop 的完整 commit hash，不用移动的 develop 代替。

材料位置：

- 开发材料自 start 起位于 `changes/unreleased/<prp-slug>/`：
  - objectives.md、design.md、delivery.json、gates/、code-review.md。
  - finish 在同一目录补齐 CHANGE.md，不搬迁；发布后随目录进入 `changes/<version>/<prp-slug>/`。
- release 材料位于 `changes/unreleased/<semver>/`：start 写入 objectives.md 与 delivery.json。
  - design 等阶段材料仅 roster ≥1 时出现。
- 代码、测试、fixture 留在项目原位置，大日志不要求提交。

路径写法：

- objectives/design 是受管可搬迁 Markdown。
- 仓内 Markdown 本地链接只相对当前文件（`./`、`../` 或同级文件名）；前导 `/` 是站点根，不是仓根。
- 搬迁时 CLI 改写仍有效的相对路径。
- delivery.json 与 gate 内路径一律仓库相对。
- fingerprint 规范化用仓库相对或 `@delivery/`，不是第二种 href 写法。

## 阶段与执行责任

主线为 start → design → [write-tests ∥ implement] → converge → code-review → finish。

- `fact-update` 是 CLI gate，只由 finish 前段内嵌的 fact update 记录；独立 `$mdf fact update`
  不记录 gate。它不是用户主线箭头上的一站。
- bugfix/hotfix/release 在 roster `0,0` 时不要求 feature 的 design、write-tests、
  implement 或 converge 阶段；roster ≥1 时与 feature 走同一主线。
- release 与 hotfix 可修复已确认的 open Bug，标为 `fixed`；不另开 bugfix 分支，也不写 bugfix child Change。
  - roster `0,0` 在 owner 上修。
  - roster ≥1 先重入 design 修订 objectives 与 design，再由各路完成。
    roster.dev ≥1 时不在 owner 实现。
- 独立 `$mdf fix` 在当前 checkout 澄清、先记录有效红灯再修复并验证单个 open Bug，标为 `fixed`。
  - 不 start、不切分支、不走交付主线、不记录 gate、不 code-review、不 finish，
    也不由 deliver 内部委托。
- 独立 `$mdf verify-fix` 对已 `fixed` 的 Bug 跑复现用例并只审这次修复。
  - release/hotfix 的 finish 在关闭这些对象前内部委托，不标 `closed`。
- code-review 的独立审查份数取冻结的 roster.reviewers（solo 默认 1，min-tdd 默认 2，pair 类默认 3）。
  - finish 集成产生的不可跳过增量新一轮为 1，不改冻结 roster。见 `references/code-review.md`。

### 触发与协调

- 用户手动触发主线 intent，或显式调用 next 委托下一阶段。
- 显式 deliver 按 `references/deliver.md` 从 start 起协调剩余阶段到 finish，
  可并行阶段按 roster 分别委托 subagent。
  - `--auto-pilot` 由主 Agent 自裁定，仅在 Gitflow 收口前确认；`--yolo` 跳过该确认。
- design 的 Baseline 与 converge 由各 intent 启动恰好 1 个 owner subagent，不计入 roster；
  deliver 步骤 4 只覆盖可并行的 qa/dev。
- 不新增独立 Owner 调度服务或统一状态协议。
- 当前执行者承担该阶段的协调与语义审查。

### worktree 与 roster

- start 始终从基线在仓库同级 `<repo-name>-worktrees/<worktree-name>` 建立交付 worktree，
  路径等于分支名；不在当前目录开分支，不 fetch、不 push。
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
- converge 由该 intent 启动恰好 1 个 owner subagent 执行集成、验证与记录；测试修改批准回主会话。
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

- 各路 stage gate 已在合入前按分支核验。
  - 同路径 `write-tests.json` / `implement.json` 冲突时保留先合入的版本。
  - qa 为 `partition` 且 ≥2 时，integrate 合完全部 qa 后写入测试 fingerprint。
    位置是 `gates/integration.json`。converge 以它判断测试是否变化。
- review 时 owner 仍汇总裁定，不按票数。

### intent 参数与 models

- `$mdf start`、`$mdf deliver` 可带 `--roster <name>`，只在尚未 start 时展开；
  已 start 后再带 `--roster` 停止。
- `$mdf start`、`$mdf design`、`$mdf deliver`、`$mdf code-review` 可带下列参数：
  - `--qa-strategy`、`--dev-strategy`、`--review-strategy`。
  - `--write-tests-model`、`--implement-model`、`--code-review-model`。
- 这些是 intent 参数，不是独立 intent。start 冻结；之后由 Agent 调用 `delivery roster` 写入。
- qa/dev strategy 在 design gate 后锁定。
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

## Gate

通过 `delivery status/check/record/verify/integrate/roster` 执行确定性操作。

- 每阶段单独保存 gates/<stage>.json，记录摘要、基线与内容 fingerprint；避免并行写同一状态文件。

| 阶段 | 前置或完成条件 |
| --- | --- |
| write-tests、implement | 只要求已提交 design |
| write-tests | 写完可编译或可加载执行的测试即完成，不要求全绿 |
| converge | 需两路完成 |
| code-review | 需收敛全绿 |
| finish | 需当前 code-review、事实审阅和验证证据有效 |

- 全绿由 converge 负责，且相对**当前交付所需 suite**，不等于 manifest 里每一条命令。
- 不能手填 passed 代替 CLI 检查。
- 语义结论不是 CLI 推理结果，summary 必须包含实际审查依据。

测试门槛与所需 suite：

- 设计 policy 的 protected_paths 覆盖所有测试、fixture、快照和工具配置，包括 named suite 的路径。
  - manifest 的 `verification` 始终属于测试门槛。
  - 路径可以是仓库相对文件、目录或 glob。
- design policy 必须另含 `suites`：本交付改动涉及的全部功能块的 named suite 名。
  - 非空列表，不得使用 lint/build/quick/smoke/release/full。
- 点名执行 test case 或 test 仅用于定位，不替代所需 suite 通过。
- `delivery verify` / `project-verify` / gate 记录必须写出 Core 实际跑过的 `suites`。

失效与补验：

- 代码和验证配置（含预算）改变使全绿失效；事实文档改变只要求事实重审和受影响验证。
- `fact-update` gate 绑定 `facts`、`implementation` 与 `design`。
  - 只改测试或验证配置不使事实审阅过期，但仍使全绿与 code-review 过期。
- `code` fingerprint 覆盖 `docs/`、`changes/`、仓根 Markdown 与 manifest 之外的全部受管文件。
  - ADR、调研、Proposal 或 Change 材料的改动不使 code-review 或全绿过期。
- 记录文件不参与其自身校验对象的 fingerprint。
- 缺失或过期时原地补验，不回退 intent。

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

### 测试报告

每次运行 suite（含 named suite）都必须产出 JUnit XML 报告。

- Core 为每次运行新建 `.mdf/reports/<时间戳>-<suite>/`，以环境变量 `MDF_REPORT_DIR` 传给入口命令，
  命令把 XML 写进该目录；lint 与 build 也各有运行目录。
- 每个运行目录都保存该命令完整的 `stdout.log` 与 `stderr.log`。
- `.mdf/reports/` 由 Core 自带 `.gitignore` 忽略，7 天前的条目自动清理，见 `common.md`「日志与报告」。
- test case 取 `<testcase>` 的 `classname`，缺失时取所在 `<testsuite>` 的 `name`；
  项目须配置运行器使其对应 test case。
- Core 解析后在同目录写 `summary.json`：test case 级的结果与用时，及其下 test 级的
  结果与用时。gate 与 code-review 证据记录报告路径与 test case 级汇总。
- 缺报告、报告无法解析、未含任何 test，或含 failure、error、skipped（含 xfail）时，
  该 suite 失败，即使命令退出码为 0。
- 点名执行 test case 或 test 只用于定位，不强制 JUnit 报告。
  有运行器报告则读报告；否则用 `mdf.py run` 落盘。

### 验证 suite

| suite | 成员 | 预算 | 何时必跑 |
| --- | --- | --- | --- |
| quick | 只含 hermetic 的 UT 与 PT | 30s | 任何改动 |
| smoke | 任意种类，包含 quick 的全部成员 | 300s | feature、bugfix 收口 |
| release | 发版所需的 test case，包含 smoke 的全部成员 | 无 | release、hotfix |
| named | 某一功能块（如 module）的 test case，均属于 full | 无 | 改动该功能块后 |

- full 指全部 test case，是 release 与各 named suite 的上界；它没有入口，不由任何
  gate 执行，名字保留、不得用作 named suite。
- 预算包含启动依赖与预热，不含 build；项目可在 manifest `budgets` 覆盖。
  test case 放进 quick 或 smoke 会超预算时，拆成多个 test case，只把合预算的部分放入。
- lint 与 build 同 quick 一样，任何改动都要跑。
- 每个 suite 在 `docs/system/testing/` 有一节或一页，写明：
  - 目的、入口命令、成员选择规则、预算、环境。
  - 点名执行 test case / test 的命令模板。

| 交付 | 阶段 | Core 必须通过 | Agent 另须通过 |
| --- | --- | --- | --- |
| feature | write-tests | 只要求可执行测试已写；不要求全绿 | — |
| feature | converge、code-review、finish | lint、build、quick、smoke | design policy `suites` 所列 named suite |
| bugfix | Verify、code-review、finish | lint、build、quick、smoke | `suites.json` 所列 named suite（≥1） |
| release / hotfix | Verify、code-review、finish | lint、build、quick、release | roster ≥1 时 design 所列 named suite |
| 任意 | 只改事实文档 | 不机械重跑业务验证；实现、测试或验证配置变更仍使对应验证过期 | — |

- release / hotfix 的 `project-verify` 同样要求 Core 通过 lint、build、quick、release。

named suite 的执行：

- named suite 不在 manifest，Core 不在门禁中执行也不核对其名称是否已文档化。
- Agent 以 `suite-run --name <suite> --command <入口命令>` 执行 `docs/system/testing/` 中该 suite
  的入口命令。
  - 把命令、结果与报告路径写进对应 gate 或 code-review 记录的 summary；
    非 feature 的 Verify 阶段写进 `changes/unreleased/<slug>/verify.md`。

named suite 的划分：

- named suite 按功能块划分并跨交付长期复用，不按 feature、迭代或交付轮次建立。
  - 名称不得取自 PRP、Bug 或交付 slug。
- 一次改动涉及几个功能块，就要修改并通过这几个功能块的 named suite：
  - feature 在 design 列出全部涉及的功能块 suite。
  - write-tests 把新用例归入所属功能块的 suite（或 quick、smoke）。
  - implement 不得擅自改测试。
- 只有出现新的功能块时才新建 named suite。
- feature、bugfix 收口只跑 smoke 与涉及的 named suite，不跑 release，更不跑 full。

非 feature 交付：

- bugfix、release、hotfix 都先测后审：审查前由 deliver 的 Verify 阶段修到全绿。
  - 之后只在指纹变化时重验，收口复用有效证据，不重跑 release suite。
  - Verify 阶段定义见 `references/deliver.md`「先测后审」；每次运行向
    `changes/unreleased/<slug>/verify.md` 追加一条记录并随该阶段提交。
- roster `0,0` 的 bugfix 不创建 design/write-tests/converge。
- bugfix 的关联文件为 `changes/unreleased/<slug>/suites.json`。
  由 Verify 阶段在其中关联修复涉及的全部功能块中**已文档化**的 named suite（≥1）。
  - 默认不得新建；经确认后先在 `docs/system/testing/` 补该 suite 的文档，再关联。
    默认模式由用户明确确认，`--auto-pilot` / `--yolo` 由主 Agent 自裁定并记录依据。

补覆盖：

- 对 feature、非 feature 与联调均适用。
- 测试或联调中，凡需改代码才能解决的问题，先判定：原来是否缺少覆盖该问题的测试。
  - 这是现场自检，不是先把控制权交回用户。
  - 缺覆盖且能补：先补能 reproduce 的用例，再改实现。
  - 优先放入 quick，其次 smoke；两者都不能放则先问用户，不得自行放入其他 suite。
    默认模式须用户确认；`--auto-pilot` / `--yolo` 自裁定并记录依据。

quick 复现：

- 触发：非 quick 用例一旦在 converge 之后失败；bugfix / release / hotfix 则为第一次跑所需 suite 之后。
  - 必须尝试补一条 quick 复现用例（hermetic 的 UT 或 PT）；原慢用例保留。
  - 这是「补覆盖」在门禁后非 quick 失败时的专项，仍须先问是否原来缺少覆盖。
  - 结果写入 code-review 本轮记录的「quick 复现」字段：已补则写用例位置，未补则写原因。
  - 非 feature 由 Verify 阶段先把结论写入 verify.md，code-review 引用该记录。
- code-review 可按既定目标自主补该用例；削弱门槛、改预期或新增豁免仍须用户批准。

## 修改与提交权限

调用交付 intent 授权其必要的设计基线、阶段提交和工作分支集成，提交使用中文 Conventional Commit。

- 只暂存当前阶段的必要路径；不得顺带提交无关用户改动。
- 可以主动提交尚未完成的阶段产出，但须准确记录未完成状态。
- 阶段提交不代表 gate 通过，不能绕过既有验收与审阅。

各 intent 对测试与验证门槛的权限：

- 首次 write-tests 按既定设计编写测试属于授权：
  - 含把用例归入 quick、smoke 或 design 声明的 named suite。
  - 含在 `docs/system/testing/` 补齐所列 named suite 的文档。
- implement 不自主修改测试；按「补覆盖」补 reproduce 用例除外。
- 按「补覆盖」把 reproduce 用例放入 quick 或 smoke 属于授权，不另走测试修改批准。
- converge 修改测试、预期、fixture、跳过规则或任何验证门槛，需用户明确批准并记录理由。
  - `--auto-pilot` / `--yolo` 由 converge 执行者自裁定并记录。
- code-review 可以依据既定目标和设计自主修复实现与测试；降低验收、改变目标/契约仍需用户确认。
- 非 feature 分支变更 manifest `verification` 或新增 named suite：默认模式需用户确认；
  `--auto-pilot` / `--yolo` 由主 Agent 自裁定并记录依据。
- 架构优化可以建议；超出当前目标不直接实施。
- 修复后在当前 intent 原地重验。

fact update 可独立运行，也由 finish 前段内部调用，其事实审阅由 fact audit 完成。
独立调用不要求交付 gate；不能因此自动进入 finish 或其他交付阶段。
