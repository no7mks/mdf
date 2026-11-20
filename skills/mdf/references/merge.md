# Merge

non-PR 模式的实际合入入口。PR mode 由 [pr](pr.md) 执行对应流程。

树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Prepare | 约束 | 核对 catch-up、consolidate 与适用 publish 已完成 | 材料、远端 tag、clean | 2 | 续办对应阶段 |
| 2 | Integrate | 约束 | target 合回工作分支，完成适用 incremental-integration | 本轮增量验收记录 | 3 | 当前循环内修复与补检 |
| 3 | Merge | 脚本 | 执行 merge，no-ff 合入目标，发布交付推送主线 | 实际 merge commit | 返回主链 | 保留现场并续办 |

```bash
python3 "$MDF_ROOT/scripts/mdf.py" merge --repo "$REPO_ROOT"
```

- 必要的历史整理遵循 `references/squash.md`，可选 squash 的 dry-run 建议由 Agent 裁定。
- merge 前 target 有新提交时，CLI 合回并返回 incremental-integration，完成验收后重试 merge。
- feature / bugfix 完成后进入 close-out。
- Gitflow release / hotfix 完成后进入 publish，再由 close-out 完成 develop 回合与清理。
- github-flow release / hotfix 的 final tag 已在 merge 前发布；本次合入后进入 close-out。
- 目标分支前进和 PR 返工采用相同的 [incremental-integration](incremental-integration.md) 验收方法。
- merge 成功后保留工作分支及 worktree，供 publish 与 close-out 核验。
