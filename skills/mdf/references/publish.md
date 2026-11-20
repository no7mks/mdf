# Publish

版本发布入口。final tag 必须为 annotated tag，并包含本版实际发布说明。

树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Prepare | 约束 | 核对已验收材料与 workflow 对应的发布 commit | consolidate、merge 或发布分支 | 2 | 续办对应阶段 |
| 2 | Publish | 脚本 | 创建 annotated final tag，核对正文并推送 | 远端 tag 对象与 commit | 3 | 保留现场，按错误续办 |
| 3 | Continue | 约束 | 核对实际发布结果，进入后续阶段 | Git 与远端状态 | 返回主链 | 保留现场 |

## 发布点

| 模式 | 发布 commit | 后续 |
| --- | --- | --- |
| Gitflow · local | merge 已合入并推送的实际 merge commit | close-out |
| Gitflow · PR | 平台确认的 PR merge commit | close-out |
| github-flow release | catch-up、consolidate 已完成的工作分支 commit | merge/pr |
| github-flow support hotfix | close-out 已核验的 support 实际 merge commit | 完成交付 |

- feature / bugfix 的交付材料留在 unreleased，后续 release 聚合并发布版本 tag。
- github-flow release 发布后工作分支继续前进，可以合入 target、解决冲突并提交增量验收记录。
- final tag 始终指向固定发布 commit；后续 merge/pr 根据该 tag 核对已发布内容的历史关系。

```bash
python3 "$MDF_ROOT/scripts/mdf.py" publish --repo "$REPO_ROOT"
```

从主 worktree 恢复 Gitflow 发布时，显式传入 `--source <原工作分支>`。

github-flow support hotfix 从主 worktree 执行 `publish --source <原 hotfix 分支> --version <version>`。
脚本从 close-out 回执读取固定合入 commit，核对其仍在远端 support 的第一父链后推送 tag。

## Annotated tag 正文

- 读取固定发布 commit 中的本版 CHANGELOG，生成版本标题和实际变更正文。
- 空版本章节、仅有标题或空分类时停止，返回 consolidate 补齐发布说明。
- 复用已有 tag 时核对类型、commit 和完整正文。远端 tag 必须与本地 tag 对象一致。
- Gitflow 在实际 merge 后推送 tag。github-flow release 在 merge 前原子推送工作分支与 tag。
- github-flow 在 push 前核对同名远端 SHA，pre-push 检查实际更新清单，保留原有 hook 行为。
- 发布失败后复用本次候选 tag 续办；需要重新同步时，由 catch-up 清理本次尚未发布的候选 tag。
- 远端发布成功但阶段记录提交失败时，重试只续办本次精确的阶段改动，保留其他现场。
