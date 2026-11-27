# 交付事实审阅

主链 fact audit（含人工 feature 的 fact update 内部委托）复用
[Fact Audit](fact-audit.md) 共用核与 [旁路](fact-audit-against.md) 的 against context，
使本地与 CI 在相同 base、文件、history 和规则下完成同一机械与语义校验。
本页不新增 CLI 参数或 gate；roster 不改变事实审阅要求。
树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve | 约束 | ready、按 resolve-base 定完整 SHA、候选状态 | 调用类型、完整 base | 2 | 停止 |
| 2 | Review | 约束 | 委托 against 五步（默认可含 LLM） | 语义证据、JSON、report-check | pass→3 | 返回问题与缺项 |
| 3 | Return | 约束 | 主链保存摘要；最终候选只返回仓外报告 | 摘要或候选 JSON | 返回调用方 | 保留现场并停止 |

## 范围与入口

- 读取 `common.md` 与 `repository-contract.md`；调用方先完成 verify 与可选 pre-gitflow-finish。
- 主链保留 ready 前置；从当前 manifest 核对 state，缺失或非 ready 即停止。
- base 按 fact-audit 的 resolve-base：start_commit → mdf-start-commit；release 用上一正式发布；
  无账本 adhoc 用固定 range.base。已明确 CI base 时用同一 SHA，并记录原交付起点。
- 将选定 base 解析为完整 SHA；本轮与修复重审固定该 SHA。
- 主链执行 `fact-audit --scope branch --base <完整 SHA>`。有 clear commit 时 CLI 输出实际比较起点。
  `skip_audit: true` 时直接返回通过结论；否则完成语义复核与 report-check。不得缩小 context 范围。
  正常交付基线或完整 clear 增量通过且 worktree clean 时，report-check 推进 clear commit；
  同内容的阻断结论使旧记录失效。局部 base 与最终候选的显式 `--against` 仅用于本轮复核。
- 首次 release 无已发布基线且无 clear 时，按已确认的显式 base 审阅。建立首个全局 clear 需 full 语义审阅。
- fact update 委托时，完整复核后仅剩结构 finding 且 warning 已处置，可返回「仅结构 finding」。
  结构分类沿用 [普通结论](fact-audit.md#s6)。

## 主链报告与进度

- `fact-audit.md` 记录实际 base SHA、被审 HEAD、指纹、JSON 与校验结果位置。
- 摘要含逐页陈述与 evidence、覆盖、warning 处置、findings；无问题也要写核对依据。
- JSON/context 在仓外；Markdown 是已完成审阅记录。
- 沿用 [报告与 objectives 归属](fact-audit.md#s6) 保存、提交和勾选；人工 feature 由 fact update 自勾。

## PR 最终候选复核

PR Prepare 在候选材料提交和必要 squash 完成后、push 前执行。

1. 再核 CI base 与远端集成；目标变化时返回 pr 的集成与补审补测。
2. 对最终候选跑共用核，覆盖候选 Change、HTML 总结及报告中的事实声明。
3. 只返回仓外 JSON 与校验结果，不重写 fact-audit.md、不勾选、不创建提交。
4. push 前再跑该 context/report 的 report-check；未通过则不 push。

- 首次 push、更新 source、会话恢复和 squash_required 重试均适用。
- CI 独立审阅同一候选；不得把本地 Markdown 摘要当作 CI 自动通过凭据。
