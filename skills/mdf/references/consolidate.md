# Consolidate

把已验收成果整理成完整、相互一致、已提交的交付材料。适用于 feature、bugfix、release 和其他交付。

树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Scope | 约束 | 核对范围与验收；release 核对 PR/MR 和 Git history | objectives、报告、diff、核对记录 | 2 | 补齐当前增量验收后继续 |
| 2 | Materials | 约束 | 整理 Change、总结、HTML 和对象处置 | 实际交付材料 | 3 | 修订材料后继续 |
| 3 | Objects | 约束 | 核对 PRP、Bug 状态；发布交付完成 bug close 与 closures | 对象记录、版本关联 | 4 | 实现需修复时回增量验收 |
| 4 | Consolidate | 脚本 | 调用 consolidate，聚合、归档、校验并提交 | CLI 结果、自勾与 commit | 返回主链 | 保留现场，修复材料后续办 |

## 材料内容

- 核对 objectives 的验收目标、实际交付范围和关联 Proposal / Bug。
- 整理 `CHANGE.md`、交付总结和 [HTML 总结](html-materials.md)，按交付契约固化。
- 核对 CR、verify、FA 和各轮增量证据；补齐引用、结论与已知偏差。
- feature / bugfix 的材料位于 `changes/unreleased/<slug>/`，Change 写明成果、outcomes 和证据；`release_notes` 按 [CHANGELOG 编写规范](changelog-writing.md) 选类与过滤 `none`。
- release 聚合 child Change，生成版本根 Change，更新 CHANGELOG 和 manifest.latest_release。
- 归档本版适用的交付材料、PRP 与 Bug，重写链接，执行结构和内容一致性校验。
- 发布交付在首次 CLI 聚合后，须按 [CHANGELOG 编写规范](changelog-writing.md) 润色本版 CHANGELOG：
  重排、校准分类、提炼升级注意、翻译内部术语并加反引号，提交后执行 `consolidate --incremental` 锁定。
  hotfix 构造 `--hotfix-change-json` 时遵循同一规范。
- 本版 CHANGELOG 必须有实际变更条目，publish 据此生成 annotated tag 正文。

## Release 变更核对

release 在步骤 1–2 核对已交付工作，补齐遗漏的 Change；Gitflow 与 github-flow 均适用。

### 固定范围

本节固定核对端点，避免把发布候选之外的工作纳入本版。

- 左端为上一正式发布 tag 对应的完整 commit SHA，不使用 code-review 的 clear commit 缩小范围。
  - 按本版 `previous_version` 取 tag；首次聚合前读发布线 manifest 的 `versioning.latest_release`，重试沿用已记 SHA。
  - 不按全仓 tag 的时间或版本大小选择，避免误取其他 support 发布线。
  - 首次发布复用已确认的初始基线；基线缺失或歧义时停止询问。
- 右端为本轮整理材料前的 release HEAD，记录完整 SHA；历史切点 release 不追随最新 trunk。
  - 核对候选可达且基线不可达的 commits，并用两端 tree diff 确认实际效果；不只看第一父链或日期。
- 候选新增实现或集成提交时，补核新增范围和既有结论；保留原基线与已完成记录。
  - github-flow 已发布候选保持固定，后续集成沿用 Incr-consolidate，不改 final tag 的发布内容。

### 来源与覆盖

本节优先使用平台记录，并用本地历史覆盖直接提交及平台记录遗漏。

1. 根据仓库 remote 识别 GitHub 或 GitLab，优先使用可用 connector/API，或已登录的 `gh` / `glab`。
   查询关联 PR/MR 的状态、链接、合入 commit、实际 diff；完整处理分页，不用列表默认页代替全部记录。
2. 仅纳入实际合入且效果属于固定候选范围的 PR/MR；核对 merge、squash 等实际合入方式与本地 commits。
   未合入、切点之后或仅标题相关的 PR/MR 不作为本版已交付成果；PR 描述只作线索。
3. 对照范围内全部 Git history、实际 diff 和已有 child Change，检查未关联 PR/MR 的直接提交及 release 内修复。
   为每项工作记录对应 Change 或排除理由；多项 PR/MR 可对应同一 Change，避免重复发布条目。

| 平台核对结果 | 处理 |
| --- | --- |
| 查询完整且关联已核实 | 记录平台证据，继续本地 history 核对 |
| 不可访问、未登录、查询失败或结果不完整 | 用本地 Git history 兜底，明确记录「PR 核对未完成」、原因与未覆盖范围；允许继续 |
| 本地历史不足，无法确定发布范围或实际成果 | 保留已查证内容并停止，不用平台标题或猜测补齐 |

### 补齐与留证

本节把核对结果写入本次交付材料，供版本聚合与后续复核使用。

- 在 release 当前材料目录保存 `release-reconciliation.md`，随材料归档到 `changes/<version>/`。
  - 记录两端 SHA、平台查询范围与来源、完成状态、兜底原因，以及 PR/MR、commit、Change 的对应表。
  - 记录直接提交、排除项及理由；兜底时保留「PR 核对未完成」，不得写成平台核对通过。
  - 对应表使用 child slug、完整 SHA、平台 URL 或归档后的稳定路径，不依赖归档前目录的相对链接。
- 已有 Change 漏项时补入原文件；缺失的独立交付按 `assets/templates/change.md` 和 [Change 契约](object-contract.md#change) 补建。
  - feature/bugfix 的目录 slug 须匹配真实 source；adhoc 或主线直合按契约命名，冲突时核对归属，不覆盖或随意换名。
  - 不补造历史 objectives、delivery 账本、PRP 或验收结果；来源或对象归属不明时停止澄清。
- release 内修复有明确 child 归属时补原 child；独立的 release 工作先记入核对记录，不创建 `source_branch: release/*` 的 child。
  - 首次 CLI 正常聚合、归档后，补入版本根 Change 的成果、`release_notes`、evidence 和 CHANGELOG；提交后再执行 `consolidate --incremental`。
  - 不提前创建版本根 Change，否则 CLI 会跳过首次聚合；上述补齐完成前不得进入 publish 或 merge/pr。
- 首次 release 聚合仍须至少一份合法 child 及实际 release notes；仅有 release 自身工作而不满足此条件时停止并报告。
  - 不制造空壳 child、不伪造 source，也不提前造版本根绕过该约束。
- 已 revert 且无剩余效果的改动、纯项目记录等写明排除理由；部分 revert 按候选保留的实际效果记录。
  - 已在 `support/*` hotfix 发布的条目合入主线后，本版 CHANGELOG 不重复照抄（确需提及则注明同步自原 patch 版本）。
  - 同步修订已有 child 的失效 `release_notes`、Proposal/Bug 引用与 outcomes；无可发布条目时用 `release_notes: none`，保留历史证据。
  - 按真实对象处置与 closures 规则处理，不让聚合把已撤回的功能或修复标为 released/closed；归属不明时先澄清。
- 缺少必要验收证据时交回当前增量验收，不能把 PR merged 当作验收通过。
- 将核对记录的归档后路径 `changes/<version>/release-reconciliation.md` 加入适用 Change 的 `evidence.artifacts`。
  - 归档后核对 root/child 的引用与实际文件一致；artifact 字符串不依赖 Markdown 链接重写。
  - 补齐后纳入版本根 Change 和 CHANGELOG。
  - 重试或增量收敛更新同一份记录，复用已补齐的 Change，不重复建档。
- 首次聚合后、发布前发现新增 child 时，将其完整材料纳入 `changes/<version>/<slug>/`，不留在 unreleased 等待自动聚合。
  - 同步版本根的 `included_changes`、正文清单、notes、evidence、outcomes，以及相关对象处置、closures 和 CHANGELOG。
  - 重写引用并核对材料完整后移除原目录；校验并提交，再执行 `consolidate --incremental`。该命令不会重新归档新增 child。
  - 已发布版本不走此补档路径，沿用 Incr-consolidate 的固定候选约束。

### CHANGELOG 关联标识

本节让可确认来源的发布条目直接链接对应 PR/MR。

- 在 child Change 的 `release_notes` 条目末尾附 Markdown 链接，随聚合进入版本根 Change 和 CHANGELOG。
  - GitHub 使用 `[pr#123](<实际 PR URL>)`；GitLab 使用 `[mr!123](<实际 MR URL>)`。
- 同一条目对应多项 PR/MR 时列出全部已确认链接并去重；已有条目也按核对结果补齐。
- 无对应 PR/MR 的直接提交不加标识；兜底时只保留可核实的关联，不从标题或任意 `#数字` 猜测。
- 版本材料已生成时同步更新原 child Change、版本根 Change 与 CHANGELOG；
  核对两者覆盖的应发布事实与已核实 PR/MR 链接一致。
  CHANGELOG 按 [CHANGELOG 编写规范](changelog-writing.md) 面向读者组织，不要求与 YAML 字符串逐字相同。

## 对象状态

| 对象与场景 | consolidate 写入 | 实际完成核验 |
| --- | --- | --- |
| 普通 feature 对应 PRP | ready → implemented | merge/pr 确认实际合入目标分支 |
| PRP 纳入发布 | implemented → released，写 released_in | publish 确认 final tag 已推送 |
| 已验证的 Bug 修复 | open → fixed，补齐 Change outcome 与证据 | 修复及适用验收通过 |
| 修复纳入确定版本 | 调用 bug close，fixed → closed，写 fixed_in | 复现验证与修复审查通过，发布版本明确 |
| github-flow support hotfix | 只记录版本根 fixed/trunk_fixes，不改维护线 Bug 副本 | merge 前从远端 trunk 核验 Trunk-First |
| 其他处置 | 按已有 rejected、replaced、deferred 等决定维护记录 | 核对理由、关联与适用归档 |

- 工作分支先准备对象状态并提交，交付完成同时依据实际 merge 和远端 tag。
- 沿用现有状态枚举；具体字段与约束见 [对象契约](object-contract.md)。
- 除 support hotfix 的只读 Bug 边界外，待收入 fixed 先委托 bug close，执行 `references/bug-close.md`。bug close 未通过时保留现场。
- Bug close 先完成复现验证和修复审查，再关闭 Bug；需要修改实现时交回当前增量验收循环。
- 准备 closures，覆盖本版 child Change 的对象结果；critical Bug 须 fixed，major 的延期须有接受记录。

## 执行

调用方先提交本次材料，CLI 入口要求 clean。feature / bugfix 由 consolidate 更新对象记录并校验材料。
发布交付由 consolidate 统一调用底层 release-closeout，复用已通过的验证报告。

```bash
python3 "$MDF_ROOT/scripts/mdf.py" consolidate --repo "$REPO_ROOT"
```

- 发布可传 `--release-date`、`--closures-json`、`--deferred-acceptance-json`。
- hotfix 另传 `--hotfix-change-json`，版本处理遵循 [Hotfix 版本](hotfix-version.md)。
- 版本聚合执行于 final tag 之前，CHANGELOG、版本根和 manifest 必须一致。
- 通过后提交材料并自勾 consolidate；下一阶段由 workflow 和分支类型确定。
- 只记录本次预期 parent 与 tree 对应的材料 commit；hook 或并发内容不算已验收成果。
- 提交身份或内容变化时保留现场，回到 catch-up 验收新增内容后重试；已勾 consolidate 不能掩盖本轮未完成记录。

## Incr-consolidate

- incremental-integration 内按本轮增量更新相关 Change、对象记录、总结与证据。
- 发布前的版本材料在原版本目录更新，并同步 CHANGELOG。完成内容编辑并提交后运行 `consolidate --incremental`。
- Gitflow 交付和 github-flow feature / bugfix 包含本步骤。
- github-flow 已发布交付只追加集成验收记录，final tag 及其中的版本材料保持固定。
- 保留已通过的 CR、verify、FA；新增实现先完成本轮增量验收，再收敛材料。

对象处置存在歧义时可选加速使用 Jev，规则见 [common.md](common.md)。
