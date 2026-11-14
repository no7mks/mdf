# Trunk PR

`$mdf trunk-pr [<slug>]` 接管 github-flow + PR mode 下本地 trunk 的未共享 commit。
纯项目记录走 `pm/*`；其余整批走 `adhoc/*`。两个 source 都经 PR/MR 合入 trunk。

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
| 2 | Check | 约束 | 按下表在返回的 worktree 检查 | 实际校验与审查证据 | 3 | 修复并复验 |
| 3 | Pull request | 约束 | 用返回的 source 委托完整的 [PR 流程](pr.md)，复用同一 PR/MR 轮询与返工 | 平台状态、关联 CI 与合并核验 | 4 | 沿用 pr 等待与返工 |
| 4 | Finish | 约束 | 委托 close-out，再返回 sync 或报告 | completed 与同步结果 | 返回调用方 | 保留现场并续办 |

## 接管与路由

```bash
python3 "$MDF_ROOT/scripts/mdf.py" trunk-pr --repo "$REPO_ROOT" --slug <slug>
```

| 返回的 `kind` | 判定 | Source 与后续检查 |
| --- | --- | --- |
| `pm` | 完整 PR diff 和每笔本地独有 commit 均符合 [项目记录路径](common.md#项目记录) | `pm/<slug>-<id>`。沿用 [PM PR 流程](pr.md#pm-分支)。 |
| `adhoc` | 其余增量，包括夹带其他路径后又 revert 的历史 | `adhoc/<slug>` 与独立 worktree。按下节准备和检查。 |

- 首次 fetch 后固定本地 head、远端 base 与唯一 merge-base。先记录 source 并从原 head 建分支，再对齐本地 trunk。
  - PM 接管使用现有干净的 trunk worktree，不创建额外 worktree。返回的 `worktree` 是 trunk worktree。
  - 在该 worktree 用 `pr --source <source>` 创建或续办 PM PR。合并后用 `finish-gitflow --source <source>` 收口。
  - `adhoc` 返回 source 的独立 worktree；其余保全规则沿用 dev-pr。
- 返回 `kind`、`source`、`worktree` 与 `next_intent`。重试沿用操作记录和同一 PR/MR，直到 close-out 完成。
- `mdf.py trunk-pr` 完成 Prepare。当前 Agent 继续执行步骤 2–4；PR 创建后调用 `pr-watch`，收到可修问题后补验并更新原 PR，再恢复轮询。
- `$mdf sync` 的已确认 PR 计划可委托本 intent，沿用同一份接管记录。

## Adhoc 验收

- 沿用 dev-pr 步骤 2 的 Change、集成、lint、审查与 fact，验证入口由 `adhoc-status` 的 `verification` 决定。
  - `quick`：PR 净 diff、source 独有 commits 与 merge resolution 均只有文档路径。执行 `verify quick`。
  - `smoke`：含其他路径或无法确认纯文档范围。执行 `verify smoke`。
  - 文档范围包括根目录、`docs/` 与 `changes/` 下的 Markdown、HTML，以及 `changes/` 下的 JSON。
  - 根 `AGENTS.md`、manifest 配置的 rule 文件和验证固定输入（含 `docs/system/testing/`）按配置处理。
  - rename 同时检查原路径与新路径；source 内 revert 不抵消早先的非文档改动。
- 集成、hook 或返工提交后重新读取 status，按最新结果补验。在 Change 中引用实际执行的 named suite 报告。
