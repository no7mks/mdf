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
│ 2 Preview branches               │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Confirm sync                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 4 Sync trunks                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 5 Report result                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 └──── 通过 ─────────→ [结束]
```

## 工作流（唯一执行契约）

读取 `references/common.md`。不要求 manifest ready。
本 intent 先授权 fetch；用户确认计划后才授权三大 trunk 的 merge（含 no-ff）与 push；
不授权删分支、rebase 或 force-push。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check root | 脚本 | 运行 `info`，解析 Git 根 | 三个版本为 3、REPO_ROOT | 2 | 停止 |
| 2 | Preview branches | 脚本 | fetch 并展示分支关系图与同步计划 | JSON branches、confirmation | 3 | 停止 |
| 3 | Confirm sync | 约束 | 用户明确确认图中的计划 | 用户确认 | 4 | 等待或取消 |
| 4 | Sync trunks | 脚本 | 确认后先拉后推，conflict 先自行解决 | JSON trunks | 5 | 无法处理才问用户 |
| 5 | Report result | 约束 | 报告 trunks 与多余分支 | 摘要含 extras | 结束 | 停止 |

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

### 预览与确认

```bash
python3 "$MDF_ROOT/scripts/mdf.py" sync --repo "$REPO_ROOT"
```

默认只 `fetch --prune` 并输出预览，不 checkout、merge 或 push。

- 三大 trunk 固定为 `master`、`develop`、`planning`；两侧 refs 都必须已存在。
- JSON `branches` 覆盖本地与 `origin` 分支的并集；每项含 local / remote tip SHA、
  ahead / behind（local 相对 remote）、relation、graph 与是否参与同步的 `sync`。
- 向用户展示每个分支的 `graph`：始终包含双方 tip，路径上的 commit 用数量折叠；
  分叉图标出共同祖先。`refs/heads/<branch>` 为 local，`refs/remotes/origin/<branch>` 为 remote。
- 按下表解释关系，并列出三大 trunk 的操作计划；其他分支只报告。

| relation | local / remote 关系 | 三大 trunk 计划与 conflict 风险 |
| --- | --- | --- |
| equal | tip 相同 | noop |
| behind | local 是 remote 祖先 | pull ff，无 merge conflict |
| ahead | remote 是 local 祖先 | pull noop、push ff，无 merge conflict |
| diverged | 双方各有独有 commit | no-ff merge 后 push；可能 conflict，不能保证无冲突 |
| local_only / remote_only | 只存在于一侧 | 其他分支仅报告，不创建另一侧 |

示例（实际 SHA、分支名与数量以 CLI 为准）：

```text
             L (local planning，ahead 1)
            /
共同祖先 B
            \
             R (remote origin/planning，local behind 1)
→ diverged：no-ff merge，可能 conflict；成功后 push
```

用户明确确认展示的计划后，使用本次预览的 `confirmation`，不得自行代答：

```bash
python3 "$MDF_ROOT/scripts/mdf.py" sync --repo "$REPO_ROOT" --confirm "$CONFIRMATION"
```

### 执行与 conflict

- confirmation 绑定目标仓库、origin fetch / push URL 与三大 trunk tip。
- 执行前再次 fetch；任一绑定项变化，CLI 以 `sync_plan_changed` 返回新预览。
  - 重新展示图与计划，重新确认；不得用新 token 自动重试。
- 占用任一 trunk 的 worktree 必须干净；缺占用者时主 worktree 须干净。
- 按序全部 pull：remote 已是祖先则 noop；可 fast-forward 则 ff；已分叉则 no-ff merge。
  - merge 与 push 使用完整 ref；全部 pull 成功后才原子 push 三者，不顺带推送 tag。
  - 禁止 rebase、force-push、删分支。
- conflict 返回 `merge_conflict`，details 含 branch、worktree、conflicts 与 Git 输出。
  - 保留 `MERGE_HEAD`、index 与文件现场，不 abort、不切走；已完成的 pull 保留。
  - Agent 在返回的 worktree 读取 base / ours / theirs 与双方 diff，先尝试保留双方意图。
  - 不得一律选 ours / theirs；意图不明或无法验证正确结果时，说明文件、分歧与方案再问用户。
  - 只暂存解决的 conflict 文件，确认无 unmerged entry，并按目标项目要求验证相关改动。
  - 验证通过后提交 `chore(sync): 合并 origin/<branch> 到 <branch>`，再次预览并展示新关系。
  - 仅本次已授权的 pull 与 merge resolution 改变 local tip、remote 未变时，可继续执行新 token；
    有其他 tip 或同步目标变化则重新确认。完成所有 pull 后才 push。
- 非 conflict 的 Git 失败读日志并报告，不当作 conflict 擅自改文件。
- `extra_local` / `extra_remote` 只报告，不拉取、不推送、不删除。

验收：执行 JSON `ok` 为 true，且含三大 trunk 的 `pull` / `push` 结果。

异常与交接：无法处理的 conflict 才向用户提问；其他失败报告现场，不声称整体完成。

<a id="s3"></a>

**报告**

向用户展示：

- 各 trunk 的 `pull`（`noop` / `ff` / `merged`）与 `push`（`noop` / `updated`）
- `extra_local` 与 `extra_remote`（可为空）；明确未对其操作

验收：摘要含三大 trunk 与两组 extras。

通过条件：结束。异常与交接：无法展示则停止。
