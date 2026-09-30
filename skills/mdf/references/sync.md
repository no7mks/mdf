# Sync

`$mdf sync` 将 `master`、`develop`、`planning` 三大 trunk 与 `origin` 对齐：
先对三大分支全部 pull，再全部 push。其他本地或远端分支只报告，不操作。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check root                     │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Sync trunks                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Report result                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止]
```

## 工作流（唯一执行契约）

读取 `references/common.md`。不要求 manifest ready。
本 intent 授权对三大 trunk 执行 fetch、merge（含 no-ff）与 push；
不授权删分支、rebase 或 force-push。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check root | 脚本 | 运行 `info`，解析 Git 根 | 三个版本为 3、REPO_ROOT | 2 | 停止 |
| 2 | Sync trunks | 脚本 | 运行 sync CLI：先拉后推三大 trunk | JSON trunks | 3 | 停止并报告 |
| 3 | Report result | 约束 | 报告 trunks 与多余分支 | 摘要含 extras | 结束 | 停止 |

`$mdf sync` 执行本流程。

## 术语与数据结构

### 根与对齐

<a id="s1"></a>

**根**

用 `git -C <目标> rev-parse --show-toplevel` 解析 `REPO_ROOT`，并核对它就是
用户要同步的目标仓库；不符或不是 Git 仓库时停止。运行
`python3 "$MDF_ROOT/scripts/mdf.py" info`，协议、工具与 schema 版本均须为
数字 `3`。不要求 manifest、ready。

验收：Git 根为用户目标、三个版本为 3。

通过条件：进入同步。异常与交接：停止，不得模拟 CLI。

<a id="s2"></a>

**同步**

```bash
python3 "$MDF_ROOT/scripts/mdf.py" sync --repo "$REPO_ROOT"
```

CLI 契约：

- 三大 trunk 固定为 `master`、`develop`、`planning`；两侧 refs 都必须已存在。
- 先 `fetch --prune`，再按序对三大分支 pull，全部成功后再原子 push 三者。
- pull：远端已是祖先则 noop；可 fast-forward 则 ff；已分叉则 no-ff merge。
  - ❌ 禁止 rebase、force-push。
- 占用任一 trunk 的 worktree 必须对已跟踪改动干净；缺占用者时主 worktree 须干净。
- 其他本地分支与 `origin` 上其他分支只列入 `extra_local` / `extra_remote`，不拉取、
  不推送、不删除。

验收：JSON `ok` 为 true，且含三大 trunk 的 `pull` / `push` 结果。

异常与交接：停止并报告 CLI 错误；已完成的 pull 保留现场，不声称整体完成。

<a id="s3"></a>

**报告**

向用户展示：

- 各 trunk 的 `pull`（`noop` / `ff` / `merged`）与 `push`（`noop` / `updated`）
- `extra_local` 与 `extra_remote`（可为空）；明确未对其操作

验收：摘要含三大 trunk 与两组 extras。

通过条件：结束。异常与交接：无法展示则停止。
