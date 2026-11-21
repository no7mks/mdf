# Sync Changelog

将已发布 support hotfix 的记录通过 pm PR 汇入 trunk。仅用于 github-flow + PR mode。

树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Prepare | 脚本 | 核发布来源，从远端 trunk 创建或恢复 pm worktree，提取本版记录 | tag、merge、版本与返回路径 | 2 | 保留现场，续办缺失阶段 |
| 2 | Check | 约束 | 核精确 diff、历史与链接，完成记录校验和审查 | 本版 changes、CHANGELOG 与报告 | 3 | 修复并复验 |
| 3 | PR | 约束 | 委托 pr，watch 原 PR、修复反馈，直到 merged 且关联 CI 收尾通过 | PR 身份、Git merge 与 CI | 4 | 等待或返工后回 2 |
| 4 | Finish | 约束 | 清理 pm 分支与 worktree，核同步结果 | 平台与远端 trunk 内容 | hotfix close-out | 保留现场续办 |

## 身份与执行目录

- 入口先沿用 deliver 的 until、授权和 PR 入口确认；独立调用使用当前 hotfix 或已确认的 source/version。
- 本 intent 属于原 hotfix 的交付，完成 pm PR 不结束 hotfix 的父 Goal。
- Agent root 始终保持原位置，不切换宿主 root 或调用切换工作区工具。
- Git 命令使用 `git -C <绝对路径>`；其他命令使用工具 workdir 或 `cd <绝对路径> && ...`。
  每条命令显式指定执行路径，不假定上一条命令改变了当前目录。
- 保留 hotfix owner 和分支，直到其自身 close-out 完成。

## 准备与范围

```bash
python3 "$MDF_ROOT/scripts/mdf.py" sync-changelog --repo "$HOTFIX_ROOT" --source "$HOTFIX_SOURCE" --version "$VERSION"
```

- CLI 核对 support merge 与远端 annotated final tag，从固定发布 commit 提取材料。
- 尚未准备同步时，从最新远端 trunk policy 判断是否必需；准备后冻结 target/provider，直到该 PR 收尾。
  后续 PR/local 切换不遗弃在途同步，也不重新打开已经完成的 hotfix。
- 首次准备只取一次固定远端 SHA，在同一快照核 policy 并冻结 base；已 closed 的交付直接核验后返回，不新建同步。
- 从远端 `workflow.trunk` 创建 `pm/patch-record-<version>` 及独立 worktree，返回 source、target 与 worktree。
- 只导入 `changes/<version>/` 和根 CHANGELOG 的该版本章节；不带代码、manifest、Bug 状态或其他版本。
- CHANGELOG 按 SemVer 降序插入，保留其他章节的原始字节和文件权限；写入前拒绝 symlink。
  同版本内容一致则复用，不一致停止并报告冲突。
- `previous_version` 保留发布时实际基线；补入旧维护线 patch 不改写后续版本基线。
- 原样导入的已发布 support 文档，其历史相对链接按固定发布树校验；Git 换行转换后仍比较同一 blob，实际改写按当前 checkout 校验。
- 记录来源与临时分支身份保存在 Git common dir。重试复用同一分支、PR 与固定发布 commit。
- 未提交的返工或中断现场保留，先读取日志、核对 diff 并完成原操作，不 reset 或覆盖。

## PR 与返工

按 [PR](pr.md) 完成记录校验、审查、提交前 squash 和完整轮询。

- 默认 CI 对该保留前缀核验固定干净 checkout、trunk policy、精确材料与路径，输出 `changelog-sync.json`。

- 在返回的 pm worktree 用 `pr --repo <pm 路径>`；不运行 trunk-pr，不使用普通 pm rework。
- 用同一 source 和 PR ID 执行 pr-watch，等待 review、CI 与平台 merge。
- 可修反馈在 pm worktree 处理；合回 trunk 用 no-ff merge，保留其他版本条目。
- 发布材料是固定事实；修复同步遗漏、冲突或检查问题，不重写 final tag 中的内容。
  反馈要求修改发布事实或代码时报告范围冲突，不夹带修改。
- closed 未 merged 不自动创建新 PR，不标为完成；中断保留 pm 和 hotfix 现场。
- 该阶段失败不回滚或重发 patch，报告“已发布，记录同步未完成”。

## 完成与清理

1. pr-watch 确认 merged 且关联 CI 收尾通过，再运行 pr 核验实际合并。
2. 本地 trunk 若有无关脏文件或未共享提交则保留现场；pm 清理以远端合入证据为准，不强制更新 trunk。
   对 pm source 调用 `finish-gitflow --repo <pm 路径> --source <pm source>`。
3. 按 [工作区清理](close-out.md#工作区清理) 核验并删除 pm 临时 worktree；不结束父流程。
4. 从原 hotfix 路径运行：

```bash
python3 "$MDF_ROOT/scripts/mdf.py" sync-changelog --repo "$HOTFIX_ROOT" --source "$HOTFIX_SOURCE" --version "$VERSION" --complete
```

- CLI 核验平台 merged、精确记录范围、远端 trunk 内容与清理结果，记录完成后返回 close-out。
- `--complete` 的调用前提是 Agent 已核验关联 CI；平台 merged 本身不代表 CI 完成。
- 返回原 hotfix 的 close-out，最终核验并清理其分支与 worktree。
