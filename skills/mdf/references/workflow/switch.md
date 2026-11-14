# 受保护 trunk 的 Workflow 切换

## 准备目标 trunk

- 先结束在途交付，并让关联 worktree 保持 clean。
- 将旧 trunk 历史、已落地的 planning，以及切离 gitflow 时已有的 develop 历史纳入目标 trunk。
  - 目标 trunk 已受保护时，先通过平台 PR/MR 落地所需历史，保留 Git ancestry。
  - 改名时，先从包含上述历史的 commit 创建远端目标分支，并在平台上配置分支保护和所需的 CI 检查。
  - 合并前确认 CI 模板已支持切换分支，并且目标 trunk 已在 push 审计的触发范围内。
- 在本地 checkout 目标 trunk，确认其 tip 与 `origin` 一致。

## 创建并合并 PR/MR

```bash
python3 "$MDF_ROOT/scripts/mdf.py" workflow switch --repo "$REPO_ROOT" --model github-flow --trunk main
git push origin codex/workflow-switch
```

- `workflow switch` 返回 `source`、`target`、`base` 和切换 `commit`，并 checkout source。目标 ref 保持在 `base`。
- 在平台向 `target` 创建同仓 PR/MR，审阅配置并完成所需检查，使用双亲的 Merge commit 合并。
  - CI 模板通过 `review.py --target` 校验 source 从当前目标 tip 出发，且只包含 MDF 生成的 manifest 和托管规则改动。
  - 目标前进时，关闭旧 PR/MR，清理旧 source 后从更新的目标 tip 重新准备切换。
- 合并后同步本地目标 trunk，清理切换 source。用 `workflow ci` 渲染新触发范围，再按项目需要更新 CI 和默认分支。

## 首次 Push 审计

- 新分支的初始创建若收到全零 `before`，审计返回 `needs-review`。由维护者核对用于创建目标分支的 SHA。
- 切换 PR/MR 合并后，使用实际 push 的 `before` 和 `after`。首次改名审计的 `before` 仍可声明旧 trunk。
- `audit-push` 核对平台 Merge 证据、实际双亲与切换内容。缺平台证据返回 `needs-review`，单亲切换返回 `direct_trunk_commit`。
- 通过校验的切换 Merge 生效后，同批后续第一父链提交按新 workflow 审计。`policy_ref` 仍报告 push 的 `before`。
