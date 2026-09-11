# Feature 交付契约

## 身份与材料

一个 feature 对应一个依赖满足的 active ready PRP。start 经内部 clarify 确认
目标、非目标、约束与可验证验收，objectives 引用 PRP，避免复制另一个需求来源。
slug 取自 PRP 文件名，start 固定使用，不随标题修改。delivery.json 记录
proposal、slug、branch、start_commit。
起点是创建 feature 前 develop 的完整 commit hash，不用移动的 develop 代替。

开发材料位于 `docs/specs/<prp-slug>/`：objectives.md、design.md、delivery.json、gates/。
finish 整体搬入 `docs/changes/unreleased/<prp-slug>/`，材料与 CHANGE.md 同级；发布后进入
`docs/changes/<version>/<prp-slug>/`。代码、测试、fixture 留在项目原位置，大日志不要求提交。
objectives/design 是受管可搬迁 Markdown。仓内 Markdown 本地链接只相对当前文件
（`./`、`../` 或同级文件名）；前导 `/` 是站点根，不是仓根。搬迁时 CLI 改写仍有效
的相对路径。delivery.json 与 gate 内路径一律仓库相对；指纹规范化用仓库相对或
`@delivery/`，不是第二种 href 写法。

## 阶段与执行责任

主线为 start → design → [write-tests ∥ implement] → converge → review → finish。
`fact-update` 是 CLI gate，由独立 `$mdf fact update` 或 finish 前段内嵌记录，
不是用户主线箭头上的一站。
feature 以外沿用各分支原有交付语义，不强制新增阶段。
用户手动触发主线 intent，或显式调用 next 委托下一阶段；不新增 Owner 调度系统。
当前执行者承担该阶段的协调与语义审查。
start 始终从基线在仓库同级 `<repo-name>-worktrees/<worktree-name>`
建立交付 worktree，路径等于分支名；不在当前目录开分支，不 fetch、不 push。
feature 固定为 squad：start 同时建立 owner 与 `qa/feature/<slug>`、`dev/feature/<slug>`
角色分支，三者同一 start 基线。design 只在 owner 提交共用代码底座；
两路不得各自再写底座。design 不创建角色 worktree。
write-tests 与 implement 切到已有 `qa/feature/<slug>` 或
`dev/feature/<slug>`，入口先 no-ff merge owner，不得在 feature 上编写测试或实现。
本地工作分支不推送。禁止 rebase，异名分支使用 no-ff；合并冲突保留现场。

## Gate

通过 `delivery status/check/record/verify/integrate` 执行确定性操作。
每阶段单独保存 gates/<stage>.json，记录摘要、基线与内容指纹；避免并行写同一状态文件。
write-tests 和 implement 只要求已提交 design。write-tests 写完可编译或可加载
执行的测试即完成，不要求全绿；全绿由 converge 负责。converge 需两路完成，
review 需收敛全绿，finish 需当前 review、事实审阅和验证证据有效。不能手填
passed 代替 CLI 检查。
语义结论不是 CLI 推理结果，summary 必须包含实际审查依据。

设计 policy 的 protected_paths 覆盖所有测试、fixture、快照和工具配置；manifest 的
verification.commands 始终属于测试门槛。路径可以是仓库相对文件、目录或 glob。
全绿按项目全部具名验证项判断；单项重跑仅用于定位，不替代全量通过。
代码和验证配置改变使全绿失效；事实文档改变只要求事实重审和受影响验证。
记录文件不参与其自身校验对象的指纹。缺失或过期时原地补验，不回退 intent。

## 修改与提交权限

调用交付 intent 授权其必要的设计基线、阶段提交和工作分支集成，提交使用中文 Conventional Commit。
只暂存当前阶段的必要路径；不得顺带提交无关用户改动。可以主动提交尚未完成的阶段产出，
但须准确记录未完成状态；阶段提交不代表 gate 通过，不能绕过既有验收与审阅。
首次 write-tests 按既定设计编写测试属于授权。implement 不自主修改测试。
converge 修改测试、预期、fixture、跳过规则或任何验证门槛，需用户明确批准并记录理由。
review 可以依据既定目标和设计自主修复实现与测试；降低验收、改变目标/契约仍需用户确认。
架构优化可以建议；超出当前目标不直接实施。修复后在当前 intent 原地重验。

fact update 可独立运行，也由 finish 前段内部调用，其事实审阅由 fact audit 完成。
独立调用不要求交付 gate；不能因此自动进入 finish 或其他交付阶段。
