# Feature 交付契约

由 deliver、start、design、write-tests、implement、converge、code-review 与 finish 读取。
规则持续适用，不是依次执行的阶段。

## 身份与材料

一个 feature 对应一个依赖满足的 active ready PRP。start 经内部 clarify 确认
目标、非目标、约束与可验证验收，objectives 引用 PRP，避免复制另一个需求来源。
slug 取自 PRP 文件名，start 固定使用，不随标题修改。delivery.json 记录
proposal、slug、branch、start_commit。
起点是创建 feature 前 develop 的完整 commit hash，不用移动的 develop 代替。

开发材料自 start 起位于 `changes/unreleased/<prp-slug>/`：objectives.md、design.md、
delivery.json、gates/、code-review.md；finish 在同一目录补齐 CHANGE.md，不搬迁；发布后随目录进入
`changes/<version>/<prp-slug>/`。代码、测试、fixture 留在项目原位置，大日志不要求提交。
objectives/design 是受管可搬迁 Markdown。仓内 Markdown 本地链接只相对当前文件
（`./`、`../` 或同级文件名）；前导 `/` 是站点根，不是仓根。搬迁时 CLI 改写仍有效
的相对路径。delivery.json 与 gate 内路径一律仓库相对；指纹规范化用仓库相对或
`@delivery/`，不是第二种 href 写法。

## 阶段与执行责任

主线为 start → design → [write-tests ∥ implement] → converge → code-review → finish。
`fact-update` 是 CLI gate，只由 finish 前段内嵌的 fact update 记录；独立 `$mdf fact update`
不记录 gate。它不是用户主线箭头上的一站。
bugfix/hotfix/release 在 roster `0,0` 时不要求 feature 的 design、write-tests、
implement 或 converge 阶段；roster ≥1 时与 feature 走同一主线。
code-review 的独立审查份数取 roster.reviewers（默认 3），见 `references/code-review.md`。
用户手动触发主线 intent，或显式调用 next 委托下一阶段；
显式 deliver 按 `references/deliver.md` 从 start 起协调剩余阶段到 finish，
可并行阶段按 roster 分别委托 subagent；`--auto-pilot` 由主 Agent 自裁定，仅在
Gitflow 收口前确认。
不新增独立 Owner 调度服务或统一状态协议。
当前执行者承担该阶段的协调与语义审查。
start 始终从基线在仓库同级 `<repo-name>-worktrees/<worktree-name>`
建立交付 worktree，路径等于分支名；不在当前目录开分支，不 fetch、不 push。
roster 在 start 时冻结，写入 `delivery.json`（有交付材料时）与
`branch.<owner>.mdf-roster`：`qa`、`dev`、`reviewers`。
owner 恒为 1。feature 默认 `1,1,3`，其他 kind 默认 `0,0,3`；四种 kind 都可改。
qa 与 dev 只能同时为 0 或都 ≥1；一侧为 0 另一侧 ≥1 时把 0 抬成 1 再冻结。
`0,0` 时测试与实现都在 owner 上做。`≥1` 时 start 按人数建立
`qa/<owner>`、`dev/<owner>`，第 2 路起为 `qa/2/<owner>`、`dev/2/<owner>`。
design 只在 owner 提交共用代码底座；两路不得各自再写底座。
design 不创建角色 worktree。
write-tests 与 implement 在对应角色树上执行，入口先 no-ff merge owner；
`0,0` 时在 owner 上编写测试与实现。qa 与 dev 互不传入路径。
同侧 ≥2 时并行互不知情；owner 选一个做 base，由该路吸收其余优点，
converge 只合入该 winner，其余丢弃。
本地工作分支不推送。禁止 rebase，异名分支使用 no-ff；合并冲突保留现场。

## Gate

通过 `delivery status/check/record/verify/integrate` 执行确定性操作。
每阶段单独保存 gates/<stage>.json，记录摘要、基线与内容指纹；避免并行写同一状态文件。
write-tests 和 implement 只要求已提交 design。write-tests 写完可编译或可加载
执行的测试即完成，不要求全绿；全绿由 converge 负责，且相对**当前交付所需
suite**，不等于 manifest 里每一条命令。converge 需两路完成，
code-review 需收敛全绿，finish 需当前 code-review、事实审阅和验证证据有效。不能手填
passed 代替 CLI 检查。
语义结论不是 CLI 推理结果，summary 必须包含实际审查依据。

设计 policy 的 protected_paths 覆盖所有测试、fixture、快照和工具配置，包括交付
suite 的路径；manifest 的 verification.commands 始终属于测试门槛。路径可以是
仓库相对文件、目录或 glob。分层后 design policy 必须另含 `suites`（非空交付
suite 名列表，不得使用 quick/full）。
单项重跑仅用于定位，不替代所需 suite 通过。`delivery verify` /
`project-verify` / gate 记录必须写出实际跑过的 `suites`；feature 不得用
「只跑了 quick」冒充已跑本交付 suite。未分层证据若无 `suites` 字段，视为
已跑 quick 与 full（与全部项相同）。
代码和验证配置改变使全绿失效；事实文档改变只要求事实重审和受影响验证。
`fact-update` gate 绑定 `facts`、`implementation` 与 `design`：只改测试或验证配置不使
事实审阅过期，但仍使全绿与 code-review 过期。
`code` 指纹覆盖 `docs/`、`changes/`、仓根 Markdown 与 manifest 之外的全部受管文件；
ADR、调研、Proposal 或 Change 材料的改动不使 code-review 或全绿过期。
记录文件不参与其自身校验对象的指纹。缺失或过期时原地补验，不回退 intent。

### Suite 与执行矩阵

协议只规定必须跑哪些 suite；suite 在仓库里如何实现由消费方决定。

| 交付 | 阶段 | 必须通过的 suite |
| --- | --- | --- |
| feature | write-tests | 仍只要求可执行测试已写；不要求全绿 |
| feature | converge、code-review、finish | 全局 quick ∪ design policy `suites` 声明的交付 suite |
| bugfix | code-review、finish | 全局 quick ∪ `suites.json` 关联的交付 suite（≥1） |
| release / hotfix | code-review、finish（及 `project-verify`） | 全局 full |
| 任意 | 只改事实文档 | 不机械重跑全部业务验证；实现 / 测试 / 验证配置变更仍使对应验证过期 |

feature 必须在 design 声明本交付 suite：把验收映射到 quick（全局 always-run）或
本交付 suite（含慢路径）。无慢用例时，本交付全量可以等于已写入 quick 的那些测试，
但仍须作为 suite 声明并在验收时重跑。write-tests 把用例写进 `suites` 所列 suite；
implement 不得擅自改测试。

bugfix 不创建 design/write-tests/converge。分层后由 code-review 步骤 1 在
`changes/unreleased/<slug>/suites.json` 关联 ≥1 个**已有**交付 suite；默认不得
新建 suite，除非用户明确确认后先在 manifest `verification.suites` 新增该 key，再关联。
不能只关联 quick 或 full。未分层时不要求该文件，行为与今天一致（跑全部项）。
分层后 `delivery verify` / `project-verify` 证据必须含 `suites`，缺失视为过期。

非 quick 用例一旦在 converge 之后失败（bugfix / release / hotfix 则为第一次跑
所需 suite 之后），必须尝试补一条 quick 复现用例并纳入 always-run；原慢用例保留。
结果写入 code-review 本轮记录的「quick 复现」字段：已补则写用例位置，未补则写
原因。code-review 可按既定目标自主补该用例；削弱门槛或改 skip/预期仍须用户批准。

## 修改与提交权限

调用交付 intent 授权其必要的设计基线、阶段提交和工作分支集成，提交使用中文 Conventional Commit。
只暂存当前阶段的必要路径；不得顺带提交无关用户改动。可以主动提交尚未完成的阶段产出，
但须准确记录未完成状态；阶段提交不代表 gate 通过，不能绕过既有验收与审阅。
首次 write-tests 按既定设计编写测试属于授权，含把用例写入 design 声明的 suite 并
在 manifest `verification.suites` 新增或更新对应 key 及成员。implement 不自主修改测试。
converge 修改测试、预期、fixture、跳过规则或任何验证门槛，需用户明确批准并记录理由。
code-review 可以依据既定目标和设计自主修复实现与测试；降低验收、改变目标/契约仍需用户确认。
非 feature 分支变更 `verification.suites` 或新增交付 suite 名，一律需用户确认。
架构优化可以建议；超出当前目标不直接实施。修复后在当前 intent 原地重验。

fact update 可独立运行，也由 finish 前段内部调用，其事实审阅由 fact audit 完成。
独立调用不要求交付 gate；不能因此自动进入 finish 或其他交付阶段。
