# Consolidate

把已验收成果整理成完整、相互一致、已提交的交付材料。适用于 feature、bugfix、release 和其他交付。

树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Scope | 约束 | 核对交付范围、已有验收和实际成果 | objectives、报告、diff | 2 | 补齐当前增量验收后继续 |
| 2 | Materials | 约束 | 整理 Change、总结、HTML 和对象处置 | 实际交付材料 | 3 | 修订材料后继续 |
| 3 | Objects | 约束 | 核对 PRP、Bug 状态；发布交付完成 bug close 与 closures | 对象记录、版本关联 | 4 | 实现需修复时回增量验收 |
| 4 | Consolidate | 脚本 | 调用 consolidate，聚合、归档、校验并提交 | CLI 结果、自勾与 commit | 返回主链 | 保留现场，修复材料后续办 |

## 材料内容

- 核对 objectives 的验收目标、实际交付范围和关联 Proposal / Bug。
- 整理 `CHANGE.md`、交付总结和 [HTML 总结](html-materials.md)，按交付契约固化。
- 核对 CR、verify、FA 和各轮增量证据；补齐引用、结论与已知偏差。
- feature / bugfix 的材料位于 `changes/unreleased/<slug>/`，Change 写明成果、outcomes 和证据。
- release 聚合 child Change，生成版本根 Change，更新 CHANGELOG 和 manifest.latest_release。
- 归档本版适用的交付材料、PRP 与 Bug，重写链接，执行结构和内容一致性校验。
- 本版 CHANGELOG 必须有实际变更条目，publish 据此生成 annotated tag 正文。

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
