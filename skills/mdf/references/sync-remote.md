# sync-remote

适用于 github-flow release，顺序为 `fact → sync-remote → publish → catch-up → pr（PR mode）→ close-out`。
同步对象为 `origin/release/<version>`。main 集成在 publish 后执行。

树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Sync | 脚本 | 执行 sync-remote，同步远端同名 release | 固定 base、remote、增量 plan | 2 | 解决冲突并提交后重试 |
| 2 | Validate | 约束 | 按 plan 完成增量审查、验证与事实补检，准备最终版本材料 | 增量报告、最终 commit | 3 | 修复后续办 2 |
| 3 | Complete | 脚本 | 用 reviewed-head 与 summary 确认验收并自勾 | 完成记录、远端 SHA | publish | 远端前进回 1 |

## 阶段内增量验收

- sync-remote 同步远端同名分支，catch-up 集成其他分支；两者均在各自步骤内完成新增改动的增量验收。
- 已通过的 lint、code-review、verify、fact audit / fact update 保持 `[x]`，原基线报告继续保留。
- 本轮的增量 lint、code-review、smart verify、paths fact 补检属于 sync-remote 内部步骤。
  按 plan 执行适用检查，新增修复继续在本步骤内补检，全部通过后才完成 sync-remote。
- 复用 catch-up 的补检规则时，阶段归属和自勾对象均为 sync-remote；catch-up 按后续流程独立执行。
- 增量 code-review 与 fact 结论追加到原报告；验证使用独立 `sync-remote-verification-report.json`。
- 远端再次前进时仅重新打开 sync-remote，保留已通过的基线步骤；按新一轮增量继续验收。

## 同步与增量验收

```bash
python3 "$MDF_ROOT/scripts/mdf.py" sync-remote --repo "$REPO_ROOT"
```

- 前置 objectives 须全勾，工作区须 clean；进入同步前完成必要 squash。
- fetch 远端同名 release；远端分支尚未存在时按本地内容继续。
- 线性历史允许 fast-forward，分歧使用 merge；冲突保留现场，解决并提交后续办。
- 返回 plan 的 review、verify、fact 三路动作，复用 [catch-up](catch-up.md) 的增量补检规则。
  所有新增代码都纳入补检；保留此前已通过的基线报告。
- 完成版本材料与 Bug closures，执行 release-closeout 并提交材料。同步开始后保留已记录的基线 commit。
  版本材料规则见 [publish](publish.md)。对补检期间新增的实现继续增量验收。
- 取得最终 commit 后，以其完整 SHA 和验收摘要完成本阶段。

```bash
python3 "$MDF_ROOT/scripts/mdf.py" sync-remote --repo "$REPO_ROOT" \
  --complete --reviewed-head <已验收的完整SHA> --summary "增量审查、验证及事实补检结论"
```

- summary 由执行者依据实际报告填写；CLI 核对 HEAD 和远端包含关系。
- 完成后自勾 sync-remote，并更新后续 catch-up 的基线；重复完成保持幂等。
- 阶段提交失败后，重试可续办本次精确的 objectives 改动，其他未提交改动须先处理。
- 完成时远端又前进则返回本阶段，重新同步并补检。远端同名分支不受本地 worktree 锁保护。

## 发布并发与恢复

- publish 再核对已验收 HEAD 和远端 SHA，任一变化均返回 sync-remote。
- publish 以显式 lease 和 atomic push 同时推送 release 与 final tag，发布 commit 必须包含预期远端 SHA。
  lease 用于并发比较，所有允许的分支更新保持已有远端历史。
- 临时 pre-push 检查实际更新清单中 release 的新旧 SHA，分支为 up-to-date 时整次发布停止。
  检查通过后继续调用原有 pre-push hook，并保留其参数、输入与退出码。
- push 被拒绝时保留本地候选 tag。需要重新同步时，仅清理本次发布记录创建且对象仍匹配的本地候选 tag。
- final tag 已在远端发布后，本阶段停止；后续集成走独立集成分支。
