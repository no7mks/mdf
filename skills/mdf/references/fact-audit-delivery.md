# 交付事实审阅

主链 fact audit（含人工 feature 的 fact update 内部委托）复用 against 流程，
使本地与 CI 在相同 base、文件、history 和规则下使用同一审阅范围与完成校验。
本页不新增 CLI 参数、配置或 gate；roster 不改变事实审阅要求。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 范围或状态缺失 ────→ [停止]
                 │
                 ▼ 已确定
┌──────────────────────────────────┐
│ 2 Review                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 未通过 ────→ [返回问题与缺项]
                 │
                 ▼ pass
┌──────────────────────────────────┐
│ 3 Return                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 主链首轮 ────→ [保存摘要并维护进度]
                 └──── 最终候选 ────→ [仓外报告交回 pr]
```

## 工作流（唯一执行契约）

主链首轮和 PR 最终候选共用同一审阅，区别仅在调用时点和结果交接。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve | 约束 | 核调用方、ready、基线和候选准备状态 | 调用类型、完整 base SHA | 2 | 停止 |
| 2 | Review | 约束 | 委托 against 五步流程 | 语义证据、JSON、report-check | pass→3 | 返回问题与缺项 |
| 3 | Return | 约束 | 主链保存摘要；最终候选只返回仓外报告 | 摘要或候选 JSON | 返回调用方 | 保留现场并停止 |

## 范围与入口

先确定调用方、交付基线和运行状态，再委托共用审阅。

- 读取 `common.md` 与 `repository-contract.md`；调用方先完成 verify 与可选 pre-gitflow-finish hook。
- 主链保留 ready 前置；从当前 manifest 核对 state，缺失或非 ready 即停止。
- 主链默认 branch；调用方给出的 paths 只能用于定位修复，完成审阅仍覆盖完整交付比较范围。
  显式 full 属于独立维护或 migrate，不经本页。
- 已明确 CI 使用的 base 时，使用同一 base；同时记录原交付起点，不把两者混称。
  - 从项目 CI workflow、调用参数或项目规则读取；不猜测 CI 使用 merge-base 还是目标 tip。
  - 未声明 CI base 时，沿用交付基线，报告「CI base 未确认」，不声称与 CI 输入一致。
- 默认交付基线依次为 delivery.start_commit、owner 的 mdf-start-commit、merge-base develop HEAD。
  release 用上一正式发布；无账本 adhoc 用固定 range.base。缺少必要基线时停止。
- release/hotfix 已准备候选版本时，复用首轮报告记录的 base SHA 和实际材料目录。
  不从候选 manifest.latest_release 推断上一正式发布，不重建 unreleased 副本；记录缺失时核实原发布历史。
- 将选定 base 解析为完整 SHA；本轮和修复重审使用这个 SHA，符号 ref 移动不暗中更换基线。

## 共用审阅

直接执行 [against 五步流程](fact-audit-against.md)，不先运行普通 Audit CLI。

1. 将日志、context 和 JSON report 放在 checkout 外，调用 `fact-audit --against <完整 SHA>`。
2. 按 context 的 paths、implementation_paths、document_paths 完成事实、覆盖与 warning 复核。
   不以 audit 内部子范围代替 context 范围；CLI clear 只能表示确定性检查完成。
3. 按共用 schema 生成 report，执行 `fact-audit-report-check`；输入变化时重建 context 并重审。
4. 只有校验退出 0、result.valid 为 true 且 decision 为 pass 才返回通过。
   校验成功但 decision 非 pass 时返回未通过，不勾 objectives，不进入 pr / close-out。

- 使用 against 的五阶段进度；事实页、实现覆盖、warning 分别报告实际复核数量与证据。
- snapshot 已包含全量契约 validation，不再另跑 strict validation。
- fact update 委托时，完整复核后仅剩结构 finding 且 warning 已处置，可返回「仅结构 finding」。
  结构分类沿用 [普通结论](fact-audit.md#s7)，不得将 incomplete 或其他 error 归为结构问题。
- 修复仍由调用方执行；再次委托时重新生成 context，不复用修复前的通过结论。
- 同一输入下共用范围和校验不保证两次 Agent 判断完全相同；不得承诺 CI 必然通过。

## 主链报告与进度

首次主链审阅完成后，由调用方保存可核对的 Markdown 摘要并维护进度。

- `fact-audit.md` 记录实际 base SHA、被审 HEAD、worktree/rules/context 指纹、JSON 与校验结果位置。
- 摘要包含逐页陈述与 evidence、实现覆盖结果、warning 处置、findings 与未完成项。
  无问题也要记录核对依据；不得只写 finding_count=0 或 warning_count=0。
- JSON/context 保存在仓外；Markdown 是已完成审阅的记录，不声称包含其自身随后写入的内容。
- 沿用 [报告与 objectives 归属](fact-audit.md#s7) 保存、提交和勾选；人工 feature 由 fact update 自勾。
  已移入 `changes/<version>/` 的候选继续在该目录保存，最终候选复核不写回这些材料。
- 新写 Change、HTML 总结、报告或其他候选材料后，不能用前一轮结果声称这些材料已经审阅。

## PR 最终候选复核

PR Prepare 在候选材料提交、候选 checkbox 更新和必要 squash 完成后，push 前执行本节。

1. 重新核对 CI base 与远端集成状态；目标变化时返回 pr 的集成和补审补测流程。
2. 对最终候选执行上方共用审阅，覆盖候选 Change、HTML 总结及已有报告中的事实声明。
3. 本轮只返回仓外 JSON 与校验结果，不重写 fact-audit.md、不再勾 objectives 或创建提交。
4. push 前再运行该 context/report 的 report-check；输入变化则重审，未通过则不 push。

- 此轮针对最终候选，不替代首次主链前置；已有材料无需重新生成，但必须纳入最终复核。
- 首次 push、更新 source、会话恢复和 squash_required 重试均适用；无新 head 的轮询与已 merged 恢复不重审。
- CI base 改变时记录新旧 SHA，按新 base 生成 context 并审阅；不能仅靠旧 context 的 report-check 放行。
- 报告齐全须检查内容非空且支持对应结论，不能只检查文件存在。
- 需修复时返回调用方，保留原始失败证据；修复和提交后重新执行本节。
- CI 独立审阅同一候选；不得把本地 Markdown 摘要当作 CI 自动通过的凭据。
- local close-out 保持交付前材料检查，不在 close-out 内补跑 audit；发现新事实问题交回主链。
