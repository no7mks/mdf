# GLOSSARY.md

## MDF

Mars Development Flow；面向 Git 仓库的版本化文档与交付流程。

## PR mode 与 CI reviewer

PR mode 使用独立 pr intent 经 GitHub Pull Request 或 GitLab Merge Request 合并，再由 close-out 续办。
CI reviewer 是在项目 runner 上执行共用 Review 协议的审查 Agent。
显式 source-commit/target-commit 调用 code-review 时执行独立只读审查，不依赖 roster 或交付材料。
审查不代替本地 code-review intent；approve、merge 与通知由项目 policy 决定。

## Jot

`docs/JOTS.md` 中尚未分诊的随手记录。它可以是想法、优化、小问题或观察；提升后才成为
Proposal 或 Bug。Jot 不是 Proposal/Bug 的 `draft` 状态，也不是 Change。

## Bug 状态

Bug 使用 `open`、`fixed`、`closed` 或 `rejected`。`fixed` 必须经
`$mdf bug close <bug-id> --fixed-in <version>` 二次验证与修复审查后转为 `closed`；
`rejected` 是终态，并由 `reject-reason` 记录拒绝原因。

## 当前事实文档

描述当前 checkout 已成立行为，并由仓库内 evidence 支持的文档。

## ASD-STE100

Simplified Technical English；由写作规则与受控词典组成的 English 技术写作标准。
MDF 的适用方式见 [文档结构规则](skills/mdf/references/doc-structure.md)。

## 基线

`manifest.baselines` 中对当前状态主题的有证据声明。

## 验证命令

`.mdf/modules.yaml` 按 module 声明的五个入口：

- `lint`、`build`。
- `quick`、`smoke`、`release` 三个 suite（含 `command` 与 `tests` glob）。
- 可选 `budgets` 覆盖 suite 预算；repo 级默认按 module 串行展开同名入口，
  可用顶层 `verification` 覆写单项。

## Module

`.mdf/modules.yaml` 中的交付单元：含 `sourceset`、`ignore`、分套件命令与可选 `named`
suite 列表。ignore 命中路径不触发 verify，也不产生 uncovered 提示。
源代码、测试源代码与文档均可通过 module ignore 排除长度及结构硬限制，不再要求超限拆分。

## Package

按目录组织的直属源文件集合，子目录独立计数；实现和测试分别统计，默认每类最多 50 个。
超限按设计职责拆分，默认每个结果每类最多 35 个；module ignore 命中文件不计。
module 的 `size_limits` 可 override 上限及拆分比例，所有适用配置共同生效；文档规则不受影响。

## `$mdf verify`

`verify [arg]`：arg 为 smart/branch/named 时按 scope 解析，否则按 named suite 名解析。

- **smart**：改动涉及的 module 跑 lint/build/quick，并由 Agent+Jev 选题
  test/testcase；converge 验收使用。
- **branch**：全 module 的 lint/build/quick + 套件。
  - feature/bugfix/hotfix→smoke，release→release；默认按 module 串行展开。
  - 写入 `verification-report.json`（不含 commit）。
  - 主链在 code-review 之后、fact audit / close-out 之前跑。
- **named**：`--suites` 指定五固定或真 named；不写 branch 证据。

## Test、test case 与 suite

- **test**：含若干断言的最小测试项，通常为函数。
- **test case**：服务于同一目标的一组 test，通常为类或文件；suite 成员的粒度。
- **suite**：test case 的集合。
  - 每个 suite 都有自己的名称；quick、smoke、release 是有固定用途的保留名称。
  - named suite 指其余项目自定义 suite，如 gitflow、planning，不是名为 named 的大集合。

## 验证 suite

- **quick**：只含 hermetic 的 UT 与 PT，预算 30s；任何改动都跑。
- **smoke**：包含 quick，可含任意种类，预算 300s；feature、bugfix、hotfix 的 branch 验证
  跑到此。
- **release**：包含 smoke，发版所需的 test case，无预算上限；仅 release 的 branch 验证跑到此。
- **named suite**：某一功能块的 test case 集合，跨交付长期复用；每个 suite 必须有
  `docs/system/testing/<name>.md`。smart 由 Agent+Jev 选题，不默认整 suite 盲跑。
  - 与保留 suite 可以重叠，也可含 smoke 之外的成员；报告使用具体 suite 名称。

预算包含启动依赖与预热，不含 build；超出预算视为失败。
**quick 复现用例**：非 quick 用例在门禁后失败时，为复现同一缺陷补进 quick 的
hermetic UT 或 PT；原慢用例保留。

## 测试报告与运行日志

测试报告与运行日志两者都保留 7 天。

- **测试报告**：每次 suite 运行写入 `.mdf/reports/<时间戳>-<suite>/` 的产物。
  - 含 JUnit XML 与 Core 生成的 `summary.json`。
  - 含 test case 级与 test 级的结果和用时。
- **运行日志**：命令完整的 stdout 与 stderr。
  - Core CLI 写 `.mdf/logs/`，验证入口写各自的运行目录。
  - 有系统或工具自带日志/报告时读那份，不另 tee。
  - 其他命令用 Core `run` 代跑。

## Hermetic

测试进程能自行拉起全部依赖，不需要预先存在的环境、凭据或网络。依赖第三方资源
或真实兄弟产品（如联调对端）的测试不是 hermetic；第三方资源不含待测产品与兄弟产品。

## CodeWiki

通过 CodeWiki MCP 生成与更新的仓库结构 Wiki。

## Jev

可选的定型判断加速（MCP tool：`choice` / `noul` / `score` / `run`）。仅在 intent
写死的步骤使用；无 Jev 时主 Agent 路径不变。会话内首次不可用可提示一行并指向
README「Jev 可选加速」。密钥用宿主 `jev auth set` 落盘，CLI 与 MCP 共用，不是
仓库契约。协议见 `skills/mdf/references/common.md`「Jev 可选加速」。

## Planning 工作区

唯一的 `planning` 分支与 `<repo-name>-worktrees/planning` worktree。

- 用于 Proposal 的新建、评审、拆分，以及 intake / jot promote 为 Proposal。
- 主 worktree 保持 develop；合入 develop 后 `$mdf start` 才看到新对象。

## Deploy 工作区

`<repo-name>-worktrees/deploy`。`$mdf to deploy` 创建或进入，并检出已有 `master`。

- 存放 gitignore 的 deploy config；不提交这些文件。
- 已跟踪改动干净才从其他分支切回 master。
- master 不存在，或已被其他 worktree 占用时停止。
- close-out 不拆除这棵树。

## Roster

一次交付在 start 时冻结的参与人数与并行策略。

- 字段：`qa`、`dev`、`reviewers`，以及 `qa_strategy`、`dev_strategy`、
  `review_strategy`；可选 `models`。
  - owner 恒为 1，不计入可选人数。
  - reviewers 是 code-review 并发人数。
- 可用 `--roster` 展开命名组合（不写入材料）；细项可覆盖展开结果：

| 组合 | 展开 |
| --- | --- |
| `solo` | `0,0,1` |
| `min-tdd` | `1,1,2` + best-of-n |
| `competing-pair` | `2,2,3` + best-of-n |
| `coop-pair` | `2,2,3` + partition |

- 默认组合：feature 默认 `min-tdd`；其他 kind 默认 `solo`。
  - release 默认 `solo` 且 reviewers 为 3、review 为 `partition`。
- qa 与 dev 只能同时为 0 或都 ≥1；一侧为 0 则抬成 1。
  - `0,0` 时测试与实现都在 owner 上做；`≥1` 时各有角色 worktree。
- qa/dev 策略：
  - 默认 `best-of-n`：同侧 ≥2 时并行互不知情，owner 选 base 由该路吸收其余优点，
    converge 只合 winner。
  - `partition`：design 派发切片，converge 按 index 全部合入。
- review 策略：默认 `replicate`（每人覆盖同一份本轮范围），可选 `partition`（切片审查）。
  - owner 汇总裁定，不按票数。
- `models` 按 intent 可选配置，键只允许 `write-tests`、`implement`、`code-review`。
  - 值为一句口语描述，可点名一个或多个模型，不要求官方 id。
  - Agent 分派该 intent 时现场解析并选用；该路有多名执行者时可把多个模型分给他们。
  - 省略该键则该路不讨论模型。
- design 的 Baseline 与 converge 各由对应 intent 启动恰好 1 个 owner subagent。
  - 不计入 roster，不可配人数。

## Fix

Change 的 `change_kind: fix` 表示小范围修正，比 feature、bugfix 更轻，不要求先建 Bug 或 Proposal。
只用于 `source_branch: develop` 或归类为 adhoc 的真实分支；后者沿用 adhoc 流程与空 proposals 要求。

## Adhoc

临时工作分支，可涉及代码、测试、文档或配置；四类 Gitflow 与 master/main/develop/planning 外的分支均归此类。

- Agent 自行选相关 slug，从 develop 建立 `adhoc/<slug>` 与独立 worktree，不绑定 PRP。
- `$mdf adhoc` 的 local objectives 为六项：工作、lint、code-review、verify smart、fact audit/update、close-out。
- roster 固定 `0,0,1`，`needs_design: false`；工作可由 Agent 完成并勾选。
- smart 成败均写 verification-report.json；本地 no-ff 合入 develop 后保留 detached worktree。
- 已有分支可无账本收口：保留真实名称与工作区，由 pr / close-out 准备 Change 与实际 evidence，不补造 delivery/objectives。
- 内部 qa/dev 角色及 backmerge 先归属原 workflow；不能独立作为 adhoc 收口。

## Deliver、until 与 confidence

`$mdf deliver` 默认自动裁定当前交付的所有 decision，默认 local 在 close-out 之前结束，PR mode 在 pr 之前结束。

- `--until <intent>`：exclusive 截止点，不执行该 intent；`--stop-at` 是别名。
- confidence：AI 对一项 decision 的置信度，范围 `[0,1]`；默认由 Jev 评分，无 Jev 时由主 Agent 评分。
  - ≥ 0.8 自动确认；< 0.8 或无法评分时请求用户确认。
  - 包括 manual slug、squash、Gitflow 与收尾 worktree 删除的决定；人工工作不由 Agent 代勾。
- 完整边界与执行规则见 [deliver](skills/mdf/references/deliver.md)。

## Yolo

`$mdf deliver --yolo`：无默认 until、无 confidence 限制；显式 until 仍生效。
不可恢复的死硬阻塞仍停止，既有验收要求不变。

## ADR

Architecture Decision Record；记录重要且已决定的长期架构取舍及其理由，不描述
当前结构。文件为 `docs/context/adr/<slug>.md`，ID 为 `adr-<slug>`；按主题打开，
不编号。

## 路由页与主题叶

路由页只做边界与链接（`docs/README.md`、`docs/user-guide/README.md`、
`docs/system/overview.md`、切面 `index.md`）；主题叶是某一主题当前事实的唯一
归属页，独立可加载。`docs/README.md` 是维护者文档入口，按要找的主题打开一份
页面，不是阅读清单，也不是 Proposal、Bug 的工作清单。

## 唯一归属

一条可观察契约只写在一份主题叶；其他页面只链接，不复述。

## 加载质量

fact audit 对文档结构的语义审阅：

- 审阅项：入口不过载、路由页只路由、唯一归属、主题拆页、读者分离、
  ADR 不复述当前结构、overview 核心模块表。
- 行数硬限制由 CLI 检查（`size.hard`）。
- `AGENTS.md` 的行数硬限制只检查 MDF 托管块，不检查整份文件。

## Proposal 状态

draft 为待评审，ready 为可交付，implemented 为已验收合入 develop，released 为已发布。
rejected 用 reject-reason 说明不实施原因；replaced 表示需求已由拆分出的 PRP 承接。

- draft 使用 Markdown；评审定稿前展示详细 HTML 并取得用户确认，定稿保存为唯一 HTML。
- 格式与交付 HTML 总结见 [HTML 工作材料](skills/mdf/references/html-materials.md)。

## Milestone 与 MVP

Milestone（里程碑）表示用户定义的阶段目标；PRP 的可选 `milestone` 属性记录阶段归属。
`depends_on` 可引用 milestone 值，表示该阶段下已无 draft 或 ready PRP。
MVP（最小可行产品）是满足最小可用或验证目的的产品范围，可作为 milestone 的目标，
不由 PRP 数量或实施顺序自动决定。

## Objectives、Report 与收敛

- **objectives**：本次交付的目标、验收与**进度唯一账本**
  （步骤 checklist；各 intent 自勾）。
  - feature 引用单个 PRP 的目标、非目标、约束与可验证验收。
  - release 写已选定工作线、本版收口范围、预发布工作、是否联调、
    非目标与可验证验收。
- **Report**：
  - 含 verification-report.json、fact 确认、code-review.md、JUnit 等。
  - 只证明做过与声称结果；**不当**阶段通行证，不做过期审判。
- **Gate 文件**（`gates/*.json`）：
  - 可选配置快照 / 并行辅助。
  - **禁止**当作进度或验收关口。
- write-tests 完成条件是测试已编写且可编译或可加载执行，不要求全绿；
  完成后自勾 objectives。
- **converge**（收敛）：核对 objectives 前置已勾，跑 smart，修到达成后自勾。
  - 「全绿」相对该 suite，不等于 `.mdf/modules.yaml` 里每一条命令。

## Collab-mode

release 的第四种工作线，由接手 Agent 在可访问两端的 workspace 中调度前后端 worktree。

- start Agent 准备本仓 release 分支与交接材料，完成后交接。
- 接手 Agent 可以修改两端代码、测试与配置，并启停两端服务和依赖。
- 不打开消息通道；两端验收、修复与收口见 [契约](skills/mdf/references/collab-mode.md)。

## 联调通道

`$mdf integrate` 服务同 worktree、跨 worktree 与 collab-mode 三种联调。不联调不进入。

同 worktree（同仓）保留角色、计划、验收、修复与收口，不打开消息通道。
collab-mode 由接手 Agent 直接调度两端，也不打开消息通道。
跨 worktree（跨仓）的消息模式才使用下面的通道。

通道是 worktree 内由 `.gitignore` 忽略的 `.integration/` 目录，只用于跨 worktree 消息模式。

- 本机对端直接写入其 `inbox/`。
- 另一台机器上的对端通过可选 HTTP 监听把请求落成同一 inbox 文件。
- 消息种类为 `ping`、`courtesy`、`ack`、`heartbeat`、`send`、`bug-request`、`end`。
  - 对端就绪后先发 `courtesy`，必须收到指向它的 `ack`；未 ack 不得继续。
  - poll 每等待 1 分钟向对端发 `heartbeat`；Agent 每轮按 [状态确认](skills/mdf/references/integration-heartbeat.md)
    对齐双方当前工作、等待依赖与下一步，避免互等。
- 通道打开后 poll 常驻直到收口或用户停止。
  - 一个 agent 只 poll 本侧 inbox，不得再启动对端的 poll。
  - 双方用通道沟通，不要只 poll 干等。
- release 的 objectives 必须写明是否走联调通道；工作线只写选中的一条。
  - 跨 worktree 消息模式每侧只改本仓；可启动本侧依赖；不得改、操作、启动或终止对端。
  - 需要时切到 worktree 后先打开通道。Goal 完成前，用户没让你停，永远不许停下来。
  - 双端验收且确认不再改代码后才允许 code-review。
  - fact audit（必要时 fact update）在 verify branch 之后、close-out 之前执行。
- 联调测试默认由客户端主导。

## 测试类别与 Code Smell

| 类别 | 含义 |
| --- | --- |
| UT | 单元测试，测内部单元 |
| IT | 集成测试，测产品真实开放的接口，一般不用 mock |
| E2E | 端到端测试，走用户最终入口 |
| PT | 属性测试，是可用于任一层级的手法 |

- 项目内的选用与失败标准由 `docs/system/testing/` 与设计约定。
- Code smell 指提示维护性或设计问题的代码特征。
  - 由 code-review 判断是否需要在当前范围修复。


## Coverage

代码覆盖测量。coverage 是可选验证入口；target 是某个 metric 的最低百分比，covered/total 是命中数与总数。
