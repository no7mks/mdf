# Start

一次只启动一个交付 kind。start 按 roster 建立 owner 与可选 qa/dev 角色分支。

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
独立调用只推进当前 intent；deliver 内部委托时完成后返回调用方，由其选择下一阶段。

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
release/hotfix 使用 `--version <semver>`。
未指定人数时 feature 默认 `--qa 1 --dev 1 --reviewers 3`，其他 kind 默认
`0 0 3`。用户可改这三个整数；一侧为 0 另一侧 ≥1 时 CLI 把 0 抬成 1。
CLI 要求 clean，且本地基线分支存在；不 fetch、不要求 origin、不 push。
feature/bugfix/release 从本地 develop 创建，hotfix 从本地 master 创建。
本地已有同名分支则失败，不检查远端。
始终从基线在仓库同级 `<repo-name>-worktrees/<worktree-name>` 建立
worktree，路径等于分支名，`/` 为嵌套目录；不在当前目录开分支、不抢占当前
checkout。roster ≥1 时按人数建立 `qa/<owner>`、`dev/<owner>`，第 2 路起为
`qa/2/<owner>`、`dev/2/<owner>`；`0,0` 只建 owner。
成功 JSON 含 `worktree`（owner）、冻结后的 `roster` 与 `roles.qa` / `roles.dev`
列表。创建失败时拆除本次已建的全部 worktree 与分支。

验收：检查、本地分支与实际工作目录。

异常与交接：创建前检查失败时不创建分支并报告 finding；创建中失败则拆除已建
worktree 与分支。不推送，不设置 upstream。
CLI 在本地 Git config 的 `branch.<完整分支名>.mdf-start-commit` 固定起点完整 hash，
供 bugfix/hotfix code-review 使用；并以 `branch.<owner>.mdf-roster` 冻结人数。
删除分支时该配置随分支删除，不设置 upstream。
feature 以及 roster ≥1 的其他 kind 在 owner 写入
`changes/unreleased/<slug>/delivery.json`（含 roster）；feature 另写目标并提交。
roster ≥1 时后续 write-tests / implement 使用 `roles` 列表中的路径。
创建成功进入 4，本步不结束。roster `0,0` 的非 feature 不创建阶段材料；bugfix
的交付 suite 关联由 code-review 步骤 1 写入，本步不写。

<a id="s4"></a>

**切换**

目标固定为步骤 3 JSON 的 owner：`worktree` 绝对路径与 `branch` 完整分支名。
qa/dev 不在本步切换。按 `references/common.md` 的「切换工作区」
规则判定当前 agent 并切到该路径与分支，向用户给出应切到的绝对路径与分支名。
未切到则留在 4，重复对应指引，不拆除已建 worktree 与分支。
独立调用通过后结束，由用户手动触发 design 或通过 next 委托。
deliver 内部委托时返回调用方。
