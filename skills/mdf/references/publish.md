# publish

适用于 github-flow 的 release 交付。顺序为 `fact → sync-remote → publish → catch-up → pr（PR mode）→ close-out`。

树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Prepare | 约束 | 核对基线、完成版本材料并提交 | objectives、CHANGELOG、clean | 2 | 修复后重试 |
| 2 | Publish | 脚本 | 执行 publish，创建并推送 final tag | 远端 tag、自勾记录 | 3 | 保留 tag，续办 2 |
| 3 | Continue | 约束 | 转入 catch-up 与主线集成 | 固定发布 commit | 返回调用方 | 保留现场 |

## 发布前准备

- 核对 publish 之前的 objectives 全部已勾，sync-remote 已验收最终内容并记录远端 SHA。
- 在 sync-remote 完成前准备版本材料与 Bug closures，执行 `release-closeout` 汇总 CHANGELOG 并归档到 `changes/<version>/`。
  版本材料准备规则见 [close-out](close-out.md)；该材料操作在 publish 前完成。
- 必要 squash 在 sync-remote 开始前完成；完成同步验收后核对 clean 工作区与最终发布内容。
- release 保持既定发布范围。main 后续改动通过发布后的独立集成分支处理。

## 执行发布

```bash
python3 "$MDF_ROOT/scripts/mdf.py" publish --repo "$REPO_ROOT"
```

- CLI 核对 sync-remote 记录的 HEAD 与远端 SHA，变化时返回 sync-remote。
- 固定当前 commit，创建 annotated final tag `v<version>`，以 lease 和 atomic push 同时推送 release 分支与 tag。
- 核对远端 tag 对象与本地一致后，自勾 publish 并提交 objectives。
- tag push 失败时保留本地 tag，重新执行同一命令续办。已发布时核验现有 tag，重复执行保持幂等。
- 远端发布成功但 objectives 提交失败时，重试可续办本次精确的勾选改动；其他未提交改动须先处理。
- 发布后的 release 仅允许记录 objectives 进度。实现或版本材料需要修正时使用新的发布版本。

## 发布后集成

- 无增量时 catch-up 按零增量直通规则完成。
- 需要与 main 对齐或处理冲突时，执行 `release-integrate` 并在其独立 worktree 中增量补检、提交 PR。
- 集成分支保留发布 commit 的历史关系，final tag 始终指向原发布内容。
- close-out 核对 tag 已发布且发布 commit 已进入目标主线，然后完成收尾。
