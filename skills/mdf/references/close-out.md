# Close-out

核验交付、发布与适用的 develop 回合，清理分支和 worktree。材料收敛由 consolidate 完成。

树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check | 约束 | 核对 merge/pr、适用 publish 与交付身份 | 实际合入、远端 tag、clean | 2 | 续办缺失阶段 |
| 2 | Finish | 脚本 | 执行 finish-gitflow，完成适用回合与分支清理 | merge、tag、source 结果 | 3 | 保留现场并续办 |
| 3 | Cleanup | 约束 | 核对结果并清理本次临时 worktree | 实际路径、clean、完成证据 | 完成返回 | 保留未确认现场 |

## 调用边界

- 每次入口与续办先核 until，沿用 deliver-policy 和已有有效授权。
- deliver 非 yolo 须先取得本 intent 的独立用户确认，不能复用 pr 的入口确认。
- 低 confidence 返回 deliver 步骤 6；yolo 无 confidence 限制，授权与范围满足后直接执行本步骤。
- 前置 hook 由主链在 fact 前执行，不在本 intent 或 `finish-gitflow` 内补跑。
- 不在 close-out 内创建 PR、轮询 CI 或准备候选材料，前置验收和材料由对应阶段完成。

## 前置与动作

- feature / bugfix 已完成 catch-up、consolidate 和实际 merge/pr。
- Gitflow 发布交付和 github-flow release 还须核对已发布 final tag 及本版 CHANGELOG。
- 走 pr 的交付由 pr 核对实际 merged 并完成关联 CI 收尾，close-out 依据已确认的平台结果续办。
- Gitflow 将固定发布 merge commit 回合 develop；回合冲突在独立回合 worktree 验收后续办。
- github-flow release 核对已发布内容和后续集成提交均进入目标主线。
- github-flow support hotfix 核对远端 support merge，清理 source 后返回 `next_intent: publish`、`source` 与 `version`。
- 清理前检查 source 的实际 tip 与已合入结果一致，远端并发新增提交保留现场。
- 对象状态由 consolidate 随交付材料准备，close-out 根据实际 merge 与发布结果确认完成。

```bash
python3 "$MDF_ROOT/scripts/mdf.py" finish-gitflow --repo "$REPO_ROOT"
```

- 从主 worktree 恢复时传入 `--source <原分支>`。
- PR 合并后细则见 [PR 合并后续办](pr-close-out.md)，local merge 细则见 [merge](merge.md)。
- adhoc 的实际合入和清理还遵循 [Adhoc 收尾](adhoc-close-out.md) 的对应交付契约。

### 工作区清理

本节统一规定 local、PR、adhoc 与 deliver 成功收尾后的临时 worktree 清理。

- CLI 先保留目录供核验；Agent 完成核验、Goal 与报告后，默认删除本次临时 owner 和 backmerge worktree，不再单独确认。
  - deliver 委托时先返回其步骤 5；adhoc 直调在本次完成核验后清理，不再回到依赖 owner 的 Select。
  - 用户明确要求保留时遵从；清理不再使用 confidence 策略。
- 仅处理本次交付已核实的路径，不扫描删除其他交付或整个 worktrees 根目录。
  - owner 使用 `retained_worktree`；null 或已移除时跳过，不重建。
  - backmerge 使用 `backmerge.worktree`；恢复结果缺项时，以已核实发布版本对应的 `codex/backmerge/<version>` 查询 worktree 清单。
  - 恢复时不得从目录名猜版本；必须确认该回合包含本次发布提交，且完整 HEAD 已进入远端 develop。

| 路径或状态 | 动作 |
| --- | --- |
| 主 worktree、planning/deploy worktree | 始终保留；按实际路径与分支绑定核对，优先于候选清单 |
| 收口未完成、证据不符、未提交改动或未结束 Git 操作 | 保留失败现场并报告，不执行删除 |
| 存在无法确认可重建或已留存的 Git 忽略文件 | 保留 worktree 并报告 |
| owner 已切换分支或 HEAD 不等于已交付 source tip | 保留并报告，不删除后续工作 |
| backmerge 分支身份不符或完整 HEAD 未进入远端 develop | 保留并报告，不删除未发布提交 |
| 本次已完成且身份、状态均符合的临时 worktree | 默认删除，不再单独确认 |

1. 从主 worktree 核对清单、身份、clean 状态及完成证据，展示待删除绝对路径；先完成所有依赖临时目录的读取。
   - 用 `git -C <保留路径> status --porcelain --ignored=matching --untracked-files=all` 检查本地文件。
   - Git 会随 worktree 删除忽略文件；先核对其中的配置、credential 与本地产出是否可重建或已留存。
2. 从主 worktree 执行 `git -C <主路径> worktree remove <保留路径>`，不引入另一个脚本。
   - 先删除 backmerge，再删除 owner；合并在最后一次 tool call 中执行，进程 cwd 必须为主 worktree。
   - 不加 `--force`；任一删除失败则停止清理，保留剩余现场并报告，不重跑 close-out。
3. 只报告实际删除和保留结果，结束本对话；后续工作在主 worktree 开新对话。
   - 清理失败不回退已完成交付，也不影响交付完成判定；不得将保留目录误报为已删除。
