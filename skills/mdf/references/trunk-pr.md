# Trunk PR

`$mdf trunk-pr [<slug>]` 是 github-flow 下的 [dev-pr](dev-pr.md)：把本地 trunk 的未共享工作移交到 adhoc，再按 PR mode 交付。
github-flow 没有 develop，受保护的 trunk 只经 PR 前进；本流程与 dev-pr 共用同一份准备、材料与验收规则。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Prepare                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 非 github-flow 或非 PR mode ────→ [拒绝并报告]
                 ├──── 已有未合并 PR ──────────────────→ 3 Pull request
                 ├──── 已 merged 待清理 ───────────────→ 4 Finish
                 ├──── 无本地增量 ─────────────────────→ [结束]
                 ├──── 现场不符 ───────────────────────→ [保留现场并报告]
                 │
                 ▼ 已保全并对齐
┌──────────────────────────────────┐
│ 2 Check                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 检查失败 ────→ [修复并补审补测]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Pull request                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 未合并 ────→ [沿用 pr 等待与返工]
                 │
                 ▼ 合并核验通过
┌──────────────────────────────────┐
│ 4 Finish                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 未完成 ────→ [保留现场并续办]
                 └──── 已完成 ────→ [返回调用方]
```

## 工作流（唯一执行契约）

读取 `references/common.md` 与 [dev-pr](dev-pr.md)；授权范围与 dev-pr 相同，目标分支换成 manifest 的 `workflow.trunk`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Prepare | 脚本 | 先核恢复；否则保全并对齐 trunk | 原 head、base、worktree 与记录 | 首次2；PR恢复3；清理4；无增量结束 | 保留现场并报告 |
| 2 | Check | 约束 | 按 dev-pr 步骤 2 补 Change，集成、lint、审查、smoke 与 fact | 实际报告与材料 | 3 | 修复并补审补测 |
| 3 | Pull request | 约束 | 委托 pr 创建或恢复同一 PR/MR | 平台状态与合并核验 | 4 | 沿用 pr 等待与返工 |
| 4 | Finish | 约束 | 委托 close-out，再返回 sync 或报告 | completed 与同步结果 | 返回调用方 | 保留现场并续办 |

## 术语与数据结构

```bash
python3 "$MDF_ROOT/scripts/mdf.py" trunk-pr --repo "$REPO_ROOT" --slug <slug>
```

- 返回 source、worktree 与 next_intent；记录位置、恢复与 slug 规则同 dev-pr。
- 本地 trunk 独有提交先保全到 `adhoc/<slug>`，再以 `reset --keep` 对齐固定的 `origin/<trunk>`。
- github-flow 的 release、hotfix 与 `pm/*` 各走对应 PR 流程。独立项目记录见 [项目记录](common.md#项目记录)。
- sync 对 github-flow 只同步 trunk 与 `support/*`，并把 non-trivial 的本地 trunk 增量委托给本 intent。
