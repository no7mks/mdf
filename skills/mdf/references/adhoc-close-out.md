# Adhoc Close-out

本页用于 adhoc 实际合入后的核验和清理。交付文档由 consolidate 收敛；合回 target、增量验收和实际合入由 merge/pr 完成。

## 决策树

```text
┌─────────────────────────┐
│ 1 Check                 │
└────────────┬────────────┘
             ├──── PR 或无账本 ────→ [委托对应流程并返回]
             ├──── 缺前置 ─────────→ [交接所属 intent]
             ├──── 已完成 ─────────→ 4 Report
             ▼
┌─────────────────────────┐
│ 2 Recheck               │
└────────────┬────────────┘
             ├──── 状态不符 ────→ [保留现场并报告]
             ▼
┌─────────────────────────┐
│ 3 Finish                │
└────────────┬────────────┘
             ├──── 失败 ────→ [读日志并报告实际状态]
             ▼
┌─────────────────────────┐
│ 4 Report                │
└────────────┬────────────┘
             ├──── 证据不符 ────→ [报告实际状态]
             └──── 核验通过 ────→ [返回调用方并公共清理]
```

## 工作流（唯一执行契约）

读取 [common](common.md)、[delivery-contract](delivery-contract.md) 与 [adhoc](adhoc.md) 的身份和调用边界，不重跑其工作流。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check | 脚本 | 核模式、身份与实际 merge | status、账本 | 2；已完成 4 | 交接前置或按模式委托 |
| 2 | Recheck | 约束 | 核已有材料、目标 merge 与 clean | reports、Git | 3 | 保留现场，报告不一致 |
| 3 | Finish | 脚本 | local finish-gitflow；PR pr-close-out | CLI 实际结果 | 4 | 读日志，报告实际状态 |
| 4 | Report | 约束 | 核清理与 merge 证据后返回 | completed、merge、路径 | 公共清理 | 不声称完成 |

### Check

- PR mode 直接执行 [合并后续办](pr-close-out.md)，返回实际结果。
  - PR 尚未 merged 时交接 pr；不在 close-out 内创建 PR、轮询 CI 或准备候选材料。
- local 运行 `mdf.py adhoc-status --repo <owner> --slug <已知slug>`。
  - `material_mode: change` 时委托 [无账本 Adhoc 收口](adhoc-change.md)；损坏账本不能改走无账本路径。
  - `completed: true` 时直接 Report。
  - 尚无 `merge_commit` 时按 `next_step` 交接；清单已完成也须先执行 merge。
  - 账本止于 consolidate，不包含 incremental-integration、merge/pr 或 close-out 勾选项。
- 缺少阶段材料时交回所属 intent；独立 close-out 报告缺项后结束，不补做被跳过的阶段。
  - catch-up 在自己的步骤内验收同名远端增量。
  - consolidate 收敛 Change、实际 evidence 与事实更新；adhoc 的 `proposals: []`，不修改 PRP。
  - merge/pr 先将 target 合回工作分支，再完成必要的 incremental-integration；保留已通过的基线步骤。

### Recheck

本阶段只核已完成交付，不新增 source 提交或把新 target 合回已交付 source。

- 核 owner clean，无未完成 merge；有问题保留现场，不 stash、reset、abort 或提交他人改动。
- 核已提交 Change 与实际交付一致，已有 code-review、smart verification 与 fact 报告通过。
  - `change_kind: adhoc` 或 `fix`，`source_branch` 与真实分支一致，`proposals: []`。
  - `verification-report.json` 的 branch 与本交付一致，`scope: smart`、`all_passed: true`。
- local 核 `merge_commit` 仍是 target 第一父链上的双亲 merge，第二父为固定 source tip。
  - target 为配置决定的 integration branch；Gitflow 默认 develop，github-flow 为 trunk。
  - 已合并材料缺损时停止报告，不退勾原账本，不补造新提交。
- PR 核原 PR 的实际合并与关联 CI 收尾，不以本地 detached 或 checklist 全勾代替。
- 沿用调用方授权；deliver 的非 yolo close-out 入口确认和 until 仍生效，不新增另一轮确认。

### Finish 与 Report

- local 运行 `mdf.py finish-gitflow --repo <owner>`；它核验已有 merge 并清理，不再次合并。
  - 失败先读 CLI 日志，报告已完成操作，保留现场；重试从 Check 核对状态。
- 再次运行同一 `adhoc-status`，要求 `completed: true`、`merge_commit` 非空。
  - local source 已删除，owner 保留且 detached 在交付 tip，目标保留实际 no-ff merge。
  - local adhoc 不 fetch、不 push、不打 tag。
  - PR 以 pr-close-out 的目标远端 merge、`remote_deleted: true` 和本地 source 清理结果为准。
- 不删除 `.mdf/`、`docs/` 产出物，已交付材料随 target 保留。
- deliver 委托先返回其完成核验；其他直调完成报告后执行公共清理，不再返回 adhoc Select。
- 成功收尾后默认删除临时 owner 和 backmerge worktree，不再单独确认。
  - 保护对象、失败保留与最后一次 tool call 按 [工作区清理](close-out.md#工作区清理) 执行。
