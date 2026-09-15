# Start

一次只启动一个交付 kind。feature 同时建立 owner 与 qa/dev 角色分支。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve branch                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ───────→ [留在 1 询问]
                 ├──── 其他种类通过 ────→ 3 Start branch
                 │
                 ▼ feature 通过
┌──────────────────────────────────┐
│ 2 Clarify objectives             │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [不写目标，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Start branch                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 创建前检查失败 ────→ [报告 finding，不创建分支]
                 ├──── 创建中失败 ────────→ [拆除已建 worktree 与分支]
                 │
                 ▼ 创建成功
┌──────────────────────────────────┐
│ 4 Switch worktree                │
└────────────────┬─────────────────┘
                 │
                 ├──── 未切到 ────→ [留在 4 等待]
                 └──── 已切到 ────→ [结束]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/common.md` 与 `references/delivery-contract.md`。
feature 的步骤 2 读取并内部执行 `references/clarify.md`，
对照 `assets/templates/objectives.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 参数 | 脚本 | 确认分支标识；feature 用 `list` 选定 PRP | 参数、list 结果 | feature 2；其他 3 | 留在 1 询问 |
| 2 | 澄清 | 约束 | 内部 clarify 目标、非目标、约束与验收 | 确认目标 | 3 | 不写目标，停止 |
| 3 | 创建 | 脚本 | 运行 start，核对本地分支与 worktree | 分支、worktree | 4 | 检查失败不创建；创建中失败拆除 |
| 4 | 切换 | 约束 | 按当前 agent 把会话切到 owner worktree | cwd、分支 | 结束 | 留在 4 等待 |

## 术语与数据结构

### 分支参数

<a id="s1"></a>

**参数**

一次只要求一个分支的类型和必要标识：feature 要 PRP ID，bugfix 要 Bug ID，
release/hotfix 要稳定 SemVer。
feature 必须绑定一个 active ready 且依赖满足、未 start 的 PRP；
分支与交付目录 slug 取自该 PRP 文件名，不得另选，也不得使用对象 ID。
bugfix 必须绑定一个 active open Bug；分支名为 `bugfix/<Bug ID>`，
不得另选 slug。
用户未指定 PRP 时运行 `list --repo "$REPO_ROOT" --type proposal --status ready`，
只把 `blocked_by` 为空且 `in_progress` 为 `false` 的条目作为候选，按 `id` 与 `title` 供用户选择；
不逐篇翻阅 `docs/proposals/`。
用户未指定 Bug 时运行 `list --repo "$REPO_ROOT" --type bug --status open`，
按 `id` 与 `title` 供用户选择；不逐篇翻阅 `docs/bugs/`。

验收：明确参数；feature 另确认 PRP，bugfix 另确认 Bug。

异常与交接：询问。不得从自然语言猜测版本。

<a id="s2"></a>

**澄清**

对照 ready PRP 与 `assets/templates/objectives.md`，
使用内部 clarify intent，议题固定为「本次 feature 交付的目标、非目标、约束与可验证验收」。
按轮次澄清该议题。
objectives 用 `[prp-001](../../../docs/proposals/<filename>)` 引用 PRP，
不另造需求来源，不改写 PRP。
PRP 的问题、范围或验收仍不足以形成本次目标时停止，不写目标，
提示 `$mdf prp review`。
共同理解确认后，将确认文本放在仓外临时文件，保持开分支前 clean。
其他种类不进入本步骤。

验收：确认目标与共同理解。

异常与交接：不写目标、不创建分支。

<a id="s3"></a>

**创建**

解析目标 Git 根为 `REPO_ROOT`；运行 `start --repo "$REPO_ROOT" --kind <kind>`，
feature 使用 `--proposal <PRP-ID> --objectives-file <步骤 2 确认文件>`，
不传 `--name`；CLI 从 PRP 文件名取出 slug。
bugfix 使用 `--bug <Bug-ID>`，不传 `--name`；CLI 用该 ID 作为分支名。
release/hotfix 使用 `--version <semver>`；
CLI 要求 clean，且本地基线分支存在；不 fetch、不要求 origin、不 push。
feature/bugfix/release 从本地 develop 创建，hotfix 从本地 master 创建。
本地已有同名分支则失败，不检查远端。
始终从基线在仓库同级 `<repo-name>-worktrees/<worktree-name>` 建立
worktree，路径等于分支名，`/` 为嵌套目录；不在当前目录开分支、不抢占当前
checkout。feature 同时建立 owner `feature/<slug>` 与角色
`qa/feature/<slug>`、`dev/feature/<slug>`；其他 kind 只建 owner。
成功 JSON 的 `worktree` 是 owner 工作目录；feature 另含 `roles`。
创建失败时拆除本次已建的全部 worktree 与分支。

验收：检查、本地分支与实际工作目录。

异常与交接：创建前检查失败时不创建分支并报告 finding；创建中失败则拆除已建
worktree 与分支。不推送，不设置 upstream。
CLI 在本地 Git config 的 `branch.<完整分支名>.mdf-start-commit` 固定起点完整 hash，
供 bugfix/hotfix code-review 使用；删除分支时该配置随分支删除，不设置 upstream。
feature CLI 另固定 start_commit，在 owner 写入 changes/unreleased/<slug>/ 的目标和身份并提交。
后续 write-tests / implement 改用 `roles` 路径。
创建成功进入 4，本步不结束。其他 kind 不创建 feature 阶段材料。

<a id="s4"></a>

**切换**

目标固定为步骤 3 JSON 的 owner：`worktree` 绝对路径与 `branch` 完整分支名。
feature 的 qa/dev 不在本步切换。已在该路径且当前分支已是 `branch` 则本步通过。
不得再 `git worktree add`，也不得只在原根 `cd` 冒充已切换。
向用户给出应切到的绝对路径与分支名。

判定当前 agent：先看本会话可用工具，再看 `$MDF_ROOT` 是否位于
`.cursor/skills`、`.codex/skills`、`.kiro/skills`、`.claude/skills` 或
`.openclaw/skills`。工具与路径冲突时以工具为准。

Cursor：立即对 owner `worktree` 调用 `move_agent_to_root`（参数
`rootPath`）。禁止 `move_agent_to_cloned_root`（会 fetch origin，本地未推送
分支会失败）。调用后必须新开 shell 再核对，不得沿用切换前的终端 cwd。
无该工具时报告缺失并留在 4，要求用户把工作区根打开为该路径。

Codex：要求用户把当前对话接到已有 owner worktree，不要再创建：
1. 点右上角 Environment 当前项（一般显示 Local）
2. Continue in 选 New local worktree，不要选 Cloud
3. 在 Hand off chat to worktree 中打开 Worktree 下拉，选名称等于
   `branch` 的已有项（如 `feature/<slug>`）
4. 不要选 Create a new worktree，也不要选 `qa/` 或 `dev/` 角色树
对话框会保持该 worktree 的既有分支。给出应选项后等待用户完成，再核对。

Kiro IDE：没有会话内切根工具。要求用户用 File > Open Folder 或
`kiro <worktree>` 打开 owner 绝对路径作为工作区根；禁止 Add Folder to
Workspace。打开后在该根继续并核对。
Kiro CLI：会话绑定启动目录。要求用户在 owner `worktree` 下重新启动
`kiro-cli`；禁止只在原会话 `cd`。

Claude Code：对 owner `worktree` 调用 `EnterWorktree`。路径不在
`.claude/worktrees/` 时需用户批准。禁止 `claude --worktree` 或在
`.claude/worktrees/` 另建副本。

其他（含 OpenClaw）：把 owner 绝对路径交给用户，要求把工作区或进程 cwd
打开到该路径后继续；禁止再创建 worktree。OpenClaw 不得用 `worktree: true`
另建 checkout，可用 `--cwd` 指向已有 owner 路径后重启。

核对必须在切换后的环境、新 shell 执行：
`git rev-parse --show-toplevel` 等于 JSON `worktree`，
`git branch --show-current` 等于 `branch`。
向用户展示这两项。未满足则留在 4，重复对应指引，不拆除已建 worktree 与分支。
通过后结束，由用户手动触发 design 或通过 next 委托。
