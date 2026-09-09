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
                 ├──── 本次有写入 ────> [复核、提交后重调 finish]
                 ├──── 交付条件未通过 ────> [报告并停止]
                 │
                 ▼ 非预览、无写入且交付条件通过
┌──────────────────────────────────┐
│ 10 Finish Gitflow                │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ────> [结束]
                 ├──── 失败/缺失 ────> [报告现场并询问]
```

## 工作流（唯一执行契约）

完整读取 `references/common.md`、`references/audit.md`、 `references/repository-contract.md` 与
`references/object-contract.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 脚本 | [检查仓库与分支](#s1) | ready、clean | 2 | 停止 |
| 2 | 范围 | 约束 | [核对交付与版本状态](#s2) | 精确范围、证据 | 已收口 4；否则 3 | 停止 |
| 3 | 材料 | 约束 | [先迁移再补写材料](#s3) | 当前事实、Change | 4 | 保留现场，停止 |
| 4 | 审阅 | 约束 | [重新委托 audit](#s4) | 本次审阅通过 | 满足交接条件 9；否则 5 | 停止并交接 |
| 5 | 输入 | 约束 | [只读准备收口输入](#s5) | 完整输入 | release 7；hotfix 6 | 停止 |
| 6 | 热修复 | 约束 | [校验结果 JSON](#s6) | 有效 JSON | 7 | 停止 |
| 7 | 对象 | 约束 | [准备 closures](#s7) | 覆盖与验证记录 | 8 | 停止 |
| 8 | 收口 | 脚本 | [执行 release-closeout](#s8) | CLI 与验证结果 | 预览结束；apply 9 | 保留现场，停止 |
| 9 | 交接 | 约束 | [核对提交与交付条件](#s9) | clean、交付条件 | 预览/有写入结束；否则 10 | 停止 |
| 10 | 合并 | 脚本 | [调用 finish-gitflow](#s10) | 合并、tag、推送 | 结束 | 报告现场并询问 |

## 术语与数据结构

### 执行约束

下列明细补充表中操作、证据与异常处理；步骤顺序和跳转只由上表规定。

<a id="s1"></a>

**入口**

解析目标 Git 根为 `REPO_ROOT`，运行 `doctor` 与 `branch`。

验收：manifest `ready`、非 detached、clean， Gitflow 分支为 `feature/*`、`bugfix/*`、`release/<semver>` 或
`hotfix/<semver>`， 以及用户是否要求预览。

<a id="s2"></a>

**范围**

写入前计算交付范围：feature/bugfix 为 `develop...HEAD`，hotfix 为 `master...HEAD`；release 要求本地 develop，
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

迁移既有 child Change 必须在任何工作区写入之前、clean 状态下完成。先核对并迁移，
再补齐步骤 2 识别的必要当前事实；feature/bugfix 同时补齐 child Change， 不建版本目录，不关闭对象，
Proposal 保持 ready， Bug 按对象契约记录状态。 迁入既有材料时要求用户确认来源目录、目标
`changes/unreleased/<slug>` 与链接重写； 源 slug 须等于分支 slug 且不得含符号链接；
目标冲突、来源含有目标或非 canonical `CHANGE.md` 时停止； 迁移只可用 `move-change`，
无材料时创建最小 Change 目录。 release/hotfix 不在此移动 child Change。 预览仅列待补材料，不写入。

验收：确认的来源、合法路径、当前事实与 child Change，或预览缺项清单。

异常与交接：保留现场并报告；预览缺少必要材料时停止。

<a id="s4"></a>

**审阅**

内部委托 `audit`：release 执行`全量审阅`，其他分支仅审阅步骤 2 的精确范围； 每次续办都重新审阅，
不复用上次语义确认。

验收：零 finding、用户当场确认 warning 和语义摘要。

通过条件：本次已有写入、已收口或 feature/bugfix 到 9。异常与交接：其余 release/hotfix 到 5；报告并停止；
非预览可修复文档，要求用户复核、commit 后重调 finish。

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
evidence 按首次出现顺序去重并追加 manifest 验证命令。apply 在目标仓库执行命令， 保持 clean 后写入；
preview 不执行命令、不写入。

验收：CLI 结果，apply 的命令结果和 clean， 或 preview 的只读摘要。

通过条件：preview 展示结果后结束，不进入 9 或 10。异常与交接：apply 到 9；保留现场供用户检查。

<a id="s9"></a>

**交接**

交接本次结果：预览只展示摘要并结束；本次有工作区改动时展示 diff 与验证结果， 要求用户复核、commit 后重调。
无写入的 release/hotfix 必须满足第 2 步已收口判定， 且第 4 步本次 audit 通过；
feature/bugfix 必须完成 child Change 与本次 audit。

验收：已提交的复查结果、当前 clean 与交付条件。

通过条件：非预览且无写入时到 10。异常与交接：报告未满足条件并停止，不执行 Git 收口。

<a id="s10"></a>

**合并**

调用 `finish-gitflow --repo "$REPO_ROOT"`。CLI fetch 后要求源分支及参与的 master/develop 与 upstream 完全一致；
feature/bugfix no-ff 合并到 develop； release/hotfix no-ff 合并到 master 后 no-ff 合并 master 到 develop，
并创建注释 `v<semver>` tag；仅这些合并自动创建 merge commit。随后原子 push、删远端及本地源分支。

验收：合并、tag 和推送结果。

异常与交接：停止并报告当前分支、已完成合并、 tag 与推送状态；冲突时 CLI abort 当前 merge，
但不得声称此前已完成的合并也被回退。 不继续推送或删分支，询问用户如何继续；必要修复仍须复核、commit 后重调。
