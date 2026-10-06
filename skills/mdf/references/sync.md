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
                 ├──── 未确认 ────→ 3 Confirm sync
                 ├──── 取消 ──────→ [停止]
                 │
                 ▼ 确认或恢复核对通过
┌──────────────────────────────────┐
│ 4 Sync trunks                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 计划变化 ─────────────────→ 2 Preview branches
                 ├──── conflict 已解决并提交 ────→ 2 Preview branches
                 ├──── conflict 无法处理 ────────→ [保留现场并询问]
                 ├──── 其他失败 ─────────────────→ [报告现场并停止]
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
| 3 | Confirm sync | 约束 | 确认或核对恢复授权 | 授权快照、核对 | 4 | 未确认留 3；取消停止 |
| 4 | Sync trunks | 脚本 | 按已确认计划同步、处理 conflict | trunks、现场 | 5 | 变化/解决回 2；无法解决询问；其余停 |
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

通过条件：进入步骤 2 预览。异常与交接：停止，不得模拟 CLI。

<a id="s2"></a>

### 预览

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

<a id="s3"></a>

### 确认

- 用户明确确认展示的计划后，记录确认原话与授权快照，不得自行代答。
  - 快照含目标仓库、origin fetch / push URL、三大 trunk 的 local / remote 完整 tip 与 `confirmation`。
  - 从预览 JSON 取 tip；用 `git remote get-url --all origin` 与 `git remote get-url --push --all origin` 取 URL。
- 未确认时留在步骤 3 等待，取消则停止。
- conflict 恢复回到本步时，对照原授权快照及本次 pull / resolution 记录：
  - 仅已授权 pull / merge resolution 改变 local tip，且原 remote tip、仓库与两组 URL 均未变，才复用授权。
  - 否则重新确认新图与计划；缺原快照或无法证明变更来源时也须重新确认。

<a id="s4"></a>

### 执行与 conflict

使用通过步骤 3 核对的本次预览 `confirmation`：

```bash
python3 "$MDF_ROOT/scripts/mdf.py" sync --repo "$REPO_ROOT" --confirm "$CONFIRMATION"
```

- confirmation 绑定目标仓库、origin fetch / push URL 与三大 trunk tip。
- 执行前再次 fetch；任一绑定项变化，CLI 以 `sync_plan_changed` 返回新预览。
  - 回步骤 2 展示新图与计划，再按步骤 3 核对授权；不得只换 token 自动重试。
- 占用任一 trunk 的 worktree 必须干净；缺占用者时主 worktree 须干净。
- 按序全部 pull：remote 已是祖先则 noop；可 fast-forward 则 ff；已分叉则 no-ff merge。
  - merge 与 push 使用完整 ref；全部 pull 成功后才原子 push 三者，不顺带推送 tag。
  - 禁止 rebase、force-push、删分支。
- conflict 返回 `merge_conflict`，details 含 branch、worktree、conflicts 与 Git 输出。
  - 保留 `MERGE_HEAD`、index 与文件现场，不 abort、不切走；已完成的 pull 保留。
  - Agent 在返回的 worktree 读取 base / ours / theirs 与双方 diff，先尝试保留双方意图。
  - 不得一律选 ours / theirs；意图不明或无法验证正确结果时，说明文件、分歧与方案再问用户。
  - 只暂存解决的 conflict 文件，确认无 unmerged entry，并按目标项目要求验证相关改动。
  - 验证通过后提交 `chore(sync): 合并 origin/<branch> 到 <branch>`，回步骤 2 预览新关系。
  - 步骤 3 核对恢复条件后才继续；完成所有 pull 后才 push。
- 非 conflict 的 Git 失败读日志并报告，不当作 conflict 擅自改文件。
- `extra_local` / `extra_remote` 只报告，不拉取、不推送、不删除。

验收：执行 JSON `ok` 为 true，且含三大 trunk 的 `pull` / `push` 结果。

异常与交接：无法处理的 conflict 才向用户提问；其他失败报告现场，不声称整体完成。

<a id="s5"></a>

**报告**

向用户展示：

- 各 trunk 的 `pull`（`noop` / `ff` / `merged`）与 `push`（`noop` / `updated`）
- `extra_local` 与 `extra_remote`（可为空）；明确未对其操作

验收：摘要含三大 trunk 与两组 extras。

通过条件：结束。异常与交接：无法展示则停止。
