# Finish

本 intent 执行实际收口，不提供预览模式。用户明确要求仅预览或只读时，说明此入口不支持并停止；
不得将只读请求视为写入、验证命令或 Gitflow 操作的授权。

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
                 ├──── 已收口且证据有效 ────→ 4 Audit
                 ├──── 状态不一致 ──────────→ [停止]
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
│ 4 Audit                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过，已收口或 feature/bugfix ────→ 9 Hand off
                 ├──── 未通过或未确认 ───────────────────→ [停止并交接]
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
                 ├──── 失败/缺失 ────→ [停止]
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
                 ├──── 主线前进，feature/bugfix ────→ 2 Integrate and review
                 ├──── 交付条件未通过 ──────────────→ [报告并停止]
                 │
                 ▼ 必要提交完成且交付条件通过
┌──────────────────────────────────┐
│ 10 Finish Gitflow                │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [报告现场并询问]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/common.md`、`references/fact-audit.md`、
`references/repository-contract.md` 与 `references/object-contract.md`。
完整读取 `references/code-review.md`；步骤 2 集成主线后内部执行所需的 code-review。
步骤 3 读取并内部执行 `references/fact-update.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 脚本 | 确认实际收口授权；运行 doctor 与 branch | ready、Gitflow 分支 | 2 | 停止 |
| 2 | 范围 | 约束 | 核对版本；no-ff 集成主线并内部执行 code-review | 集成、审查、版本 | 已收口 4；否则 3 | 停止 |
| 3 | 材料 | 约束 | 先委托 fact update，再按分支整理并提交材料 | 事实、gate、Change | 4 | 保留现场，停止 |
| 4 | 审阅 | 约束 | 运行 gate 检查；过期原地补验后复核 | 有效证据 | 已收口或 feature/bugfix 9；待收口 5 | 停止并交接 |
| 5 | 输入 | 约束 | 只读核对 child Change、日期及热修复输入 | 完整收口输入 | release 7；hotfix 6 | 停止 |
| 6 | 热修复 | 约束 | 校验 hotfix 结果 JSON 的字段与非空要求 | 有效 JSON | 7 | 停止 |
| 7 | 对象 | 脚本 | 用 `list` 列 unreleased Bug，准备 closures 并取得用户接受 | 完整覆盖、接受记录 | 8 | 停止 |
| 8 | 收口 | 脚本 | 确认 clean，实际运行 release-closeout | 退出 0、产物与 diff | 9 | 保留现场，停止 |
| 9 | 交接 | 约束 | 提交本次产物并核对交付条件 | clean、证据 | 有效 10；需重集成 2 | 报告并停止 |
| 10 | 合并 | 脚本 | 运行 finish-gitflow，核对合并、tag 与发版推送 | Git 实际结果 | 结束 | 报告现场并询问 |

## 术语与数据结构

### 交付范围与审阅

<a id="s1"></a>

**入口**

解析目标 Git 根为 `REPO_ROOT`，运行 `doctor` 与 `branch`。

验收：manifest `ready`、非 detached， Gitflow 分支为 `feature/*`、`bugfix/*`、`release/<semver>` 或
`hotfix/<semver>`， 实际收口授权；只读请求在本步骤停止。

<a id="s2"></a>

**范围**

先识别本次相关未提交改动，按公共规则复核并提交后确定交付范围；范围不明时先澄清。
写入前按 code-review 记录固定交付范围：feature/bugfix/hotfix 为分支 start_commit 到 HEAD；
release 为上一正式发布版本的固定 commit 到 HEAD，另核对全部 child Change。
检查代码、配置、schema、测试、当前事实、Proposal、 Bug、Change，识别应更新文档。 release/hotfix 同时检查
`changes/<version>/CHANGE.md` 与 manifest： 版本根不存在，
且 latest_release 为 null 或按稳定 SemVer 比较小于目标版本时，判为待收口。 版本根已跟踪、 已提交，
且 version、 change_kind、source_branch 与当前分支完全一致、latest_release 等于目标版本时，
运行 full validation 并核对版本根证据仍覆盖当前交付结果；通过才判为已收口。
版本根提交后有未纳入收口的交付改动、 记录缺损或状态不一致时停止，不覆盖版本目录。

待收口或 feature/bugfix 在当前交付分支先集成目标主线，再核对审查证据：

- feature/bugfix 使用本地 develop，不 fetch、不 push；release/hotfix 使用 master，
  先 fetch origin 并核对本地 master/develop 与远端一致，不自动覆盖分歧。
- 确认 clean，记录目标主线的完整 commit；若它尚不是当前 HEAD 的祖先，
  在交付分支运行 `git merge --no-ff <目标commit>`。禁止 rebase，不在主线上解决交付冲突。
- 冲突时保留 merge 现场，Agent 按已确认目标、设计及两侧改动自动尝试 resolve，
  逐项核对后提交 merge。不得整侧覆盖或削弱测试来消除冲突；语义不明、需变更目标或
  无法解决时才停止询问，报告冲突与已尝试的修复。
- 只要本次集成产生新提交，无论是否冲突，都以集成后的 HEAD 重新执行完整 code-review：
  保留固定 base_commit，重新固定 review_head，启动三份独立全量审查，完成裁定、修复、
  复核与全量项目验证。不复用集成前报告，也不将集成当作旧审查的修复续办。
- 主线已包含且审查证据有效时无需重复合并或审查；证据缺失或过期时内部执行 code-review，
  通过后继续本次 finish。feature 仍须满足 code-review 的 design/converge 前置条件。

四种分支均须有完整且有效的三份独立审查、主 Agent 裁定、修复复核与验证记录。
已收口 release/hotfix 只核对已有集成与审查证据；若需要新集成或实现修改，停止报告收口状态不一致，
不得覆盖版本目录或改写已开始发布的源提交。

验收：精确实现与文档路径、目标主线已包含、集成后的审查与验证、版本状态。

通过条件：待收口或 feature/bugfix 到 3， 已收口到 4。异常与交接：报告缺项或不一致并停止。这是交付前检查，
不是 audit。

<a id="s3"></a>

**材料**

先委托 `references/fact-update.md`，传入步骤 2 的交付范围，
同步受影响当前事实并内部完成 fact audit，再执行必要验证。release 的事实审阅使用全量范围。
仅 feature 在委托前运行 `delivery check --stage fact-update`，确认 code-review 有效；使用 start_commit
到 HEAD 的固定范围，并由 fact update 记录 fact-update gate。调用方统一提交本次事实与证据。
按分支准备材料：

- feature：在 `changes/unreleased/<slug>/` 补齐唯一 PRP 对应的 canonical CHANGE.md，
  与 objectives、design、gates 同级；材料不搬迁。CHANGE.md 整理完成后提交，再进入阶段校验。
- bugfix：按对象契约准备当前分支的 `changes/unreleased/<slug>/CHANGE.md`，
  slug 为 Bug ID 的 kebab-case（小写）；
  不要求 objectives、design、唯一 PRP 或 feature gate。记录实际 Bug outcomes 和证据。
- release：核对已有 child Change，材料聚合与版本目录写入留给步骤 8。
- hotfix：不创建 child Change，实际结果 JSON 留给步骤 6 校验。

feature/bugfix 不建版本目录。feature 在成功合入 develop 的 merge commit 中转换为 implemented；
bugfix 的对象状态按既有契约处理。release/hotfix 按后续收口步骤管理版本与对象。

验收：事实一致性、有效 gate、规范 Change 和链接检查。

异常与交接：保留现场；缺少前置阶段时报告，不自动执行被跳过的主线 intent。

<a id="s4"></a>

**审阅**

feature 运行 `delivery check --stage finish`，使用本次有效 code-review、事实与验证证据。
其他分支运行 `project-verify check --repo "$REPO_ROOT"`。
两者返回 `stale_gate`、`stale_verification` 或证据过期时，在本步骤原地补验补审后复核，
不回退步骤；语义或实现变化必须补审补验。其他失败走本步骤的失败去向。
从步骤 2 直接进入的已收口 release/hotfix 重新委托 fact audit。
其他分支使用步骤 3 的本次 fact audit 结论；release 为全量，其他分支为范围审阅。

验收：各分支 code-review 证据有效，feature 无缺失或过期 gate；事实审阅及 full validation 通过。

通过条件：已收口 release/hotfix 或 feature/bugfix 到 9；待收口 release/hotfix 到 5。
本次是否写入不改变该分流；相关材料先按公共规则提交，再继续收口。

### 版本收口输入与执行

<a id="s5"></a>

**输入**

只读准备收口输入：release 读取全部 unreleased child Change，移动留给第 8 步 CLI； hotfix 必须没有 child Change，
且提供实际结果 JSON；两者均提供规范 `--release-date`。

验收：完整版本收口输入。

通过条件：release 到 7， hotfix 到 6。异常与交接：停止。Core 记录确定性审计，语义审阅使用本次已确认 audit。

<a id="s6"></a>

**热修复**

校验 hotfix `--hotfix-change-json`：必填 body、release_notes、evidence；
可选 proposals、fixed、closed、 deferred、adrs、breaking。body 非空，三类 evidence 字符串列表合计至少一条，
release notes 至少一项非空。

验收：有效 JSON。

异常与交接：未知字段、空字符串或缺字段时停止。Core 注入 change_kind 与 source_branch。

<a id="s7"></a>

**对象**

准备 `--closures-json`，覆盖每个 child Change outcome，并可补录未写 child Change 的对象；本步不写对象。
运行 `list --repo "$REPO_ROOT" --type bug --status open --status fixed`，取 `found_in` 为 `unreleased`
的条目作为待分类清单，不逐篇翻阅 `docs/bugs/`。
对每个 active 且 `found_in: unreleased` 的 Bug 分类： fixed 经二次验证后由 CLI 关闭并写 fixed_in，
rejected 使用既有 reject-reason， deferred 保持 open；critical 仅 fixed；
major deferred/wont-fix 要用户接受、理由和 follow-up； duplicate 不进 outcome，canonical 与 duplicate 一并归档。

验收：完整 closures 与验证、 接受记录。

<a id="s8"></a>

**收口**

调用 `release-closeout`；版本根 Change 聚合 child outcomes/evidence，
evidence 按首次出现顺序去重并追加 manifest 验证命令。CLI 操作前要求 clean；
主动提交本次必要材料，不夹带无关改动。运行实际收口，在目标仓库执行验证命令，保持 clean 后写入。

验收：CLI 退出 0、命令结果、收口产物和完整 diff。

通过条件：成功到 9。异常与交接：失败保留现场并停止，报告命令结果与实际写入。

### 提交与 Gitflow

<a id="s9"></a>

**交接**

由 Agent 复核并提交本次事实、Change、收口材料与阶段证据，同次继续；
feature/bugfix 不 push，运行 finish gate 检查后进入本地 Gitflow 合并。
release/hotfix 仍需已提交收口结果，finish 将发版推送到 origin。
feature/bugfix 必须有规范 child Change。
按 code-review 的证据规则再次核对最终 HEAD，防止收口期间的实现改动遗漏审查。
再次核对步骤 2 的目标主线仍被最终 HEAD 包含；主线前进时，feature/bugfix 回到步骤 2
重新集成、审查并更新事实材料；release/hotfix 无论是否已收口均停止并报告状态不一致，
不重新集成、不覆盖版本目录。
核对 clean 与当前证据后进入 Gitflow 合并，不自动处理无关改动。

验收：必要提交、当前 clean 和交付条件。

<a id="s10"></a>

**合并**

调用 `finish-gitflow --repo "$REPO_ROOT"`。feature/bugfix 不 fetch、不 push；
no-ff 合并到本地 develop，删除本地源分支。角色分支仍在则失败。
release/hotfix 要求 origin；首次调用 fetch 后要求本地 master/develop 与远端一致；
no-ff 合并到 master，创建注释 `v<semver>` tag，再 no-ff 合并 master 到 develop，
原子 push `master`、`develop` 与 tag。不推送、不删除远端 `release/*`/`hotfix/*`。
若当前位于 `<repo-name>-worktrees/` 下的交付 worktree，合并后移除该 worktree。

验收：合并、tag 与（release/hotfix 的）推送结果。

异常与交接：停止并报告当前分支、已完成合并、 tag 与推送状态；冲突时 CLI abort 当前 merge，
但不得声称此前已完成的合并也被回退。 不继续推送或删分支，询问用户如何继续；
必要修复按确认范围由 Agent 复核并提交；后续 Git 操作按用户决定继续。

release/hotfix 首次发布前，CLI 在 Git common dir 的 `mdf/finish/<完整分支名>.json`
保存源提交、origin、目标起点及后续进度。失败后取得用户继续决定，再调用同一命令；
若源 worktree 已删除或当前已不在原分支，从主 worktree 调用 `finish-gitflow --repo <主路径> --source <原分支>`。
脚本逐项核对记录与实际本地/远端引用，跳过已完成合并与 tag；推送结果丢失时先查询远端，
完全一致则仅继续清理。release/hotfix 分支存在期间 develop 可继续前进；续办时若 develop
尚无合并记录且本地与 origin/develop 一致，以当前 develop 刷新记录中的合并基线，
再 no-ff 合并 master；精确匹配原基线与 master 双亲的未记录合并直接恢复，不重复合并。
master 仍严格核对原基线；最终原子推送前的远端校验使用刷新后的 develop 基线。
记录、源提交、origin 或目标引用冲突时返回 `publish_state_changed`，
停止并报告，不重置分支、不覆盖 tag、不盲目重推。完成记录保留供清理中断后续办。
