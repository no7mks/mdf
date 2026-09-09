# Finish

用户要求预览时全程只读；不补写文档、不移动 Change、不修改对象、不执行验证命令，
不合并、打 tag、push 或删除分支。缺少预览输入时报告缺项并停止。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check entry                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────> [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Resolve delivery               │
└────────────────┬─────────────────┘
                 │
                 ├──── 已收口且证据有效 ────> 4 Audit
                 ├──── 状态不一致 ────> [停止]
                 │
                 ▼ 待收口或 feature/bugfix
┌──────────────────────────────────┐
│ 3 Prepare materials              │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────> [保留现场，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 4 Audit                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过，有写入或已收口或 feature/bugfix ────> 9 Hand off
                 ├──── 未通过或未确认 ────> [停止并交接]
                 │
                 ▼ 通过，待收口且无写入的 release/hotfix
┌──────────────────────────────────┐
│ 5 Prepare closeout               │
└────────────────┬─────────────────┘
                 │
                 ├──── release 输入完整 ────> 7 Prepare closures
                 ├──── 输入缺失 ────> [停止]
                 │
                 ▼ hotfix 输入完整
┌──────────────────────────────────┐
│ 6 Check hotfix                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────> [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 7 Prepare closures               │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────> [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 8 Close release                  │
└────────────────┬─────────────────┘
                 │
                 ├──── preview 成功 ────> [展示预览并结束]
                 ├──── 失败 ────> [保留现场并停止]
                 │
                 ▼ apply 成功
┌──────────────────────────────────┐
│ 9 Hand off                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 预览 ────> [展示预览并结束]
                 ├──── 交付条件未通过 ────> [报告并停止]
                 │
                 ▼ 非预览、必要提交完成且交付条件通过
┌──────────────────────────────────┐
│ 10 Finish Gitflow                │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ────> [结束]
                 ├──── 失败/缺失 ────> [报告现场并询问]
```

## 工作流（唯一执行契约）

完整读取 `references/common.md`、`references/fact-audit.md`、 `references/repository-contract.md` 与
`references/object-contract.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 脚本 | [检查仓库与分支](#s1) | ready、分支 | 2 | 停止 |
| 2 | 范围 | 约束 | [核对交付与版本状态](#s2) | 精确范围、证据 | 已收口 4；否则 3 | 停止 |
| 3 | 材料 | 约束 | [先同步事实再整理材料](#s3) | 当前事实、Change | 4 | 保留现场，停止 |
| 4 | 审阅 | 约束 | [检查本次审阅证据](#s4) | 本次审阅通过 | 满足交接条件 9；否则 5 | 停止并交接 |
| 5 | 输入 | 约束 | [只读准备收口输入](#s5) | 完整输入 | release 7；hotfix 6 | 停止 |
| 6 | 热修复 | 约束 | [校验结果 JSON](#s6) | 有效 JSON | 7 | 停止 |
| 7 | 对象 | 约束 | [准备 closures](#s7) | 覆盖与验证记录 | 8 | 停止 |
| 8 | 收口 | 脚本 | [执行 release-closeout](#s8) | CLI 与验证结果 | 预览结束；apply 9 | 保留现场，停止 |
| 9 | 交接 | 约束 | [核对提交与交付条件](#s9) | clean、交付条件 | 预览结束；否则 10 | 停止 |
| 10 | 合并 | 脚本 | [调用 finish-gitflow](#s10) | 合并、tag、推送 | 结束 | 报告现场并询问 |

## 术语与数据结构

### 执行约束

下列明细补充表中操作、证据与异常处理；步骤顺序和跳转只由上表规定。

<a id="s1"></a>

**入口**

解析目标 Git 根为 `REPO_ROOT`，运行 `doctor` 与 `branch`。

验收：manifest `ready`、非 detached， Gitflow 分支为 `feature/*`、`bugfix/*`、`release/<semver>` 或
`hotfix/<semver>`， 以及用户是否要求预览。

<a id="s2"></a>

**范围**

非预览先识别本次相关未提交改动，按公共规则复核并提交后确定交付范围；范围不明时先澄清。
预览不提交，列出未提交内容对交付范围的影响。
写入前计算交付范围：feature 为记录的 start_commit 到 HEAD，bugfix 为 `develop...HEAD`，hotfix 为 `master...HEAD`；
release 要求本地 develop，
以当前 checkout 和全部 child Change 为交付范围。
检查代码、配置、schema、测试、当前事实、Proposal、 Bug、Change，识别应更新文档。 release/hotfix 同时检查
`changes/<version>/CHANGE.md` 与 manifest： 版本根不存在，
且 latest_release 为 null 或按稳定 SemVer 比较小于目标版本时，判为待收口。 版本根已跟踪、 已提交，
且 version、 change_kind、source_branch 与当前分支完全一致、latest_release 等于目标版本时，
运行 full validation 并核对版本根证据仍覆盖当前交付结果；通过才判为已收口。
版本根提交后有未纳入收口的交付改动、 记录缺损或状态不一致时停止，不覆盖版本目录。

验收：精确实现与文档路径、版本状态及校验结果。

通过条件：待收口或 feature/bugfix 到 3， 已收口到 4。异常与交接：报告缺项或不一致并停止。这是交付前检查，
不是 audit。

<a id="s3"></a>

**材料**

预览仅列待补材料，不写入、不执行验证。非预览先委托 `references/fact-update.md`，
同步受影响当前事实并内部完成 fact audit，再执行必要验证。
feature 在此之前运行 `delivery check --stage fact-update`，确认 review 有效；使用 start_commit
到 HEAD 的固定范围。fact update 完成后记录 fact-update gate，并提交事实与证据。
`move-change` 操作前要求 clean；不得夹带无关改动来满足前置条件。
将 .specs/<slug> 用 move-change 整体移动到 changes/unreleased/<slug>；续办时识别已移动记录。
补齐唯一 PRP 对应的 canonical CHANGE.md，材料和 CHANGE.md 同级。搬迁链接由 CLI 重写。
搬迁和 CHANGE.md 整理完成后提交这些材料，再进入阶段校验，避免用未提交路径作为设计基线。
feature/bugfix 不建版本目录。feature 在成功合入 develop 的 merge commit 中转换为 implemented；
bugfix 的对象状态按既有契约处理。release/hotfix 按后续收口步骤管理版本与对象。

验收：事实一致性、有效 gate、规范 Change、搬迁和链接检查。

异常与交接：保留现场；缺少前置阶段时报告，不自动执行被跳过的主线 intent。

<a id="s4"></a>

**审阅**

feature 运行 `delivery check --stage finish`，使用本次有效 review、事实与验证证据。
材料移动后如 evidence 路径发生变化，执行 full validation 并检查链接；语义或实现变化必须补审补验。
从步骤 2 直接进入的已收口 release/hotfix 重新委托 fact audit。
其他分支使用步骤 3 的本次 fact audit 结论；release 为全量，其他分支为范围审阅。

验收：不存在缺失或过期 gate，full validation 通过。

<a id="s5"></a>

**输入**

只读准备收口输入：release 读取全部 unreleased child Change，移动留给第 8 步 CLI； hotfix 必须没有 child Change，
且提供实际结果 JSON；两者均提供规范 `--release-date`， 仅用户要求预览时加 `--dry-run`。

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
对每个 active 且 `found_in: unreleased` 的 Bug 分类： fixed 经二次验证后由 CLI 关闭并写 fixed_in，
rejected 使用既有 reject-reason， deferred 保持 open；critical 仅 fixed；
major deferred/wont-fix 要用户接受、理由和 follow-up； duplicate 不进 outcome，canonical 与 duplicate 一并归档。

验收：完整 closures 与验证、 接受记录。

<a id="s8"></a>

**收口**

调用 `release-closeout`；版本根 Change 聚合 child outcomes/evidence，
evidence 按首次出现顺序去重并追加 manifest 验证命令。closeout CLI（含 dry-run）操作前要求 clean；
预览不提交，若被未提交内容阻塞则报告。非预览主动提交本次必要材料，不夹带无关改动。
apply 在目标仓库执行命令，保持 clean 后写入；
preview 不执行命令、不写入。

验收：CLI 结果，apply 的命令结果和 clean， 或 preview 的只读摘要。

通过条件：preview 展示结果后结束，不进入 9 或 10。异常与交接：apply 到 9；保留现场供用户检查。

<a id="s9"></a>

**交接**

预览结束。非预览由 Agent 复核并提交本次事实、Change、收口材料与阶段证据，同次继续；
feature 按既有权限推送并运行 finish gate 检查。其他分支的阶段提交若需额外推送才能同步 upstream，
须取得该推送授权；不要求用户手动提交或仅因本次写入而重调。
release/hotfix 仍需已提交收口结果；feature/bugfix 必须有规范 child Change。
核对 clean、upstream 与当前证据后进入 Gitflow 合并，不自动处理无关改动。

验收：必要提交、当前 clean 和交付条件。

<a id="s10"></a>

**合并**

调用 `finish-gitflow --repo "$REPO_ROOT"`。CLI fetch 后要求源分支及参与的 master/develop 与 upstream 完全一致；
feature/bugfix no-ff 合并到 develop； release/hotfix no-ff 合并到 master 后 no-ff 合并 master 到 develop，
并创建注释 `v<semver>` tag；仅这些合并自动创建 merge commit。随后原子 push、删远端及本地源分支。

验收：合并、tag 和推送结果。

异常与交接：停止并报告当前分支、已完成合并、 tag 与推送状态；冲突时 CLI abort 当前 merge，
但不得声称此前已完成的合并也被回退。 不继续推送或删分支，询问用户如何继续；
必要修复按确认范围由 Agent 复核并提交；后续 Git 操作按用户决定继续。
