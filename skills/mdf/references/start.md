# Start

一次只启动一个交付 kind。start 按 roster 建立 owner 与可选 qa/dev 角色分支。
开分支前展示并确认将冻结的 roster。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve branch                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ─────────────→ [留在 1 询问]
                 ├──── bugfix/hotfix 通过 ────→ 3 Confirm roster
                 │
                 ▼ feature/release 通过
┌──────────────────────────────────┐
│ 2 Clarify objectives             │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [不写目标，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Confirm roster                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 未决 ────→ [留在 3]
                 ├──── 拒绝 ────→ [停止]
                 │
                 ▼ 确认
┌──────────────────────────────────┐
│ 4 Start branch                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 创建前检查失败 ────→ [报告 finding，不创建分支]
                 ├──── 创建中失败 ────────→ [CLI 已回滚，报告并停止]
                 │
                 ▼ 创建成功
┌──────────────────────────────────┐
│ 5 Switch worktree                │
└────────────────┬─────────────────┘
                 │
                 ├──── 未切到 ────→ [留在 5 等待]
                 └──── 已切到 ────→ [结束]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/common.md` 与 `references/delivery-contract.md`。
feature 与 release 的步骤 2 读取并内部执行 `references/clarify.md`。
分别对照 `assets/templates/objectives.md` 与 `assets/templates/release-objectives.md`。
独立调用只推进当前 intent；deliver 内部委托时完成后返回调用方，由其选择下一阶段。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve branch | 脚本 | 确认标识；feature 用 list 选 PRP | 参数、list | feature/release 2；其他 3 | 留在 1 询问 |
| 2 | Clarify objectives | 约束 | 内部 clarify 目标、非目标、约束与验收 | 确认目标 | 3 | 不写目标，停止 |
| 3 | Confirm roster | 约束 | 展示 member、strategy 与 models 并确认 | 用户明确确认 | 4 | 拒绝停止；未决留 3 |
| 4 | Start branch | 脚本 | 运行 start，核对分支与 worktree | 分支、worktree | 5 | 检查失败不创建；中途失败已回滚并停 |
| 5 | Switch worktree | 约束 | 按当前 agent 把会话切到 owner worktree | cwd、分支 | 结束 | 留在 5 等待 |

## 术语与数据结构

### 分支参数

<a id="s1"></a>

**参数**

一次只要求一个分支的类型和必要标识：

- feature 要 PRP ID，bugfix 要 Bug ID，release/hotfix 要稳定 SemVer。
- feature 与 release 还要确认的 objectives；start 不为 bugfix/hotfix 写 objectives。
  - bugfix：roster `0,0` 时不需要；roster ≥1 时由 design 的 Baseline 补写。
  - hotfix 始终记录已确认的热修复范围：roster `0,0` 由 deliver 在开发前确认并写入，
    roster ≥1 由 design 的 Baseline 写入。
- feature 必须绑定一个 active ready 且依赖满足、未 start 的 PRP。
  - 分支与交付目录 slug 取自该 PRP 文件名，不得另选，也不得使用对象 ID。
- bugfix 必须绑定一个 active open Bug；分支名为 `bugfix/<Bug ID>`，不得另选 slug。
  - ⚠️ 已锁定的 release 或 hotfix 上修复 Bug 不走本 intent，不创建 bugfix 分支。
- release 必须绑定稳定 SemVer；本版范围是 start 时已在 develop 的 child Change。
  - 不得把新 PRP 当作本版实现范围。
- 用户未指定 PRP 时运行 `list --repo "$REPO_ROOT" --type proposal --status ready`：
  - 只把 `blocked_by` 为空且 `in_progress` 为 `false` 的条目作为候选。
  - 按 `id` 与 `title` 供用户选择；不逐篇翻阅 `docs/proposals/`。
- 用户未指定 Bug 时运行 `list --repo "$REPO_ROOT" --type bug --status open`：
  - 按 `id` 与 `title` 供用户选择；不逐篇翻阅 `docs/bugs/`。

验收：明确参数；feature 另确认 PRP，bugfix 另确认 Bug，release 另确认版本与目标。

异常与交接：询问。不得从自然语言猜测版本。

### 目标澄清

<a id="s2"></a>

**澄清**

feature 与 release 按下列规则澄清；hotfix 与 bugfix 不进入本步骤。

- feature：
  - 对照 ready PRP 与 `assets/templates/objectives.md`。
  - 使用内部 clarify intent，议题固定为「本次 feature 交付的目标、非目标、约束与可验证验收」。
  - objectives 用 `[prp-001](../../../docs/proposals/<filename>)` 引用 PRP，
    不另造需求来源，不改写 PRP。
  - PRP 的问题、范围或验收仍不足以形成本次目标时停止，不写目标，提示 `$mdf prp review`。
- release：
  - 对照 `changes/unreleased/` 中非 SemVer 子目录的 child Change，
    以及 `assets/templates/release-objectives.md`。
  - 使用内部 clarify intent，议题固定为「本版工作线、收口范围、预发布工作、非目标与可验证验收」。
  - 工作线按是否联调二选一，开分支前必须选定：
    - 不联调：`start → 开发 → verify → code-review → finish`
    - 联调：`start → 开通道 → 对齐计划 → 本端验收 → 双端验收 → 确认无更多代码修改后 → code-review → finish`
  - 目标只写入已选定的那一条；不罗列未选路径，不写「本版选定…」。
  - fact update 由 finish 前段执行，不画进工作线箭头。
  - 本版范围写入 start 时的 child Change 清单。
  - 跨仓 pin 写 repo 与 branch/commit/version；仓外联调证据的记录方式写入验收。
  - ✅ 允许在本分支改 Bug、配置、文档与联调证据。
  - ❌ 不得实施新 PRP，缺能力则推迟或作废本次 release，回 develop 开 feature。
- 共同理解确认后，将确认文本放在仓外临时文件，保持开分支前 clean。

验收：确认目标与共同理解。

异常与交接：不写目标、不创建分支。

### Roster 确认

<a id="s3"></a>

**确认**

解析将冻结的 roster：

- 未指定 `--roster` 时的默认值：
  - feature 默认 `min-tdd`。
  - release 默认 `solo` 加 3 名 partition reviewer。
  - bugfix 与 hotfix 默认 `solo`。
- 再叠加本次以下参数与对话中已确认的人数：
  - `--qa-strategy`、`--dev-strategy`、`--review-strategy`
  - `--write-tests-model`、`--implement-model`、`--code-review-model`
- 对话里口语点名的模型（可多个、不要求官方 id）写入对应 `--*-model` 一句字符串。
- 一侧为 0 另一侧 ≥1 时把 0 抬成 1。
- 未指定细项策略时随 named roster：
  - solo/min-tdd/competing-pair 为 `best-of-n`+`replicate`。
  - coop-pair 为 qa/dev `partition`。
- `--roster` 取值：`solo` / `min-tdd` / `competing-pair` / `coop-pair`。

向用户展示以下内容：

- named roster（显式名称或 kind 默认）。
- member：owner 恒为 1，以及 `qa`、`dev`、`reviewers` 人数与将创建的 qa/dev 角色分支。
  - `0,0` 只建 owner。
- strategy：`qa_strategy`、`dev_strategy`、`review_strategy`。
- 若本次带了任一 `--*-model`，按 intent 展示对应字符串（口语，可多个模型）。
  - 未带的 intent 不写、不问、不提。

确认规则：

- 用户可改人数或策略；改后按上列规则重新展示，不得静默沿用旧值。
- 📌 必须取得明确确认才进入创建；不得把沉默当作同意。
- 由 `$mdf deliver --auto-pilot` 或 `--yolo` 委托时本步按已给参数与上述默认值自裁定，
  不向用户提问。

验收：用户明确确认将冻结的 roster。

异常与交接：拒绝则停止，不创建分支；未决或非明确答复留在 3。

### 创建与切换

<a id="s4"></a>

**创建**

解析目标 Git 根为 `REPO_ROOT`；运行 `start --repo "$REPO_ROOT" --kind <kind>`，按 kind 追加参数：

| kind | 追加参数 | 说明 |
| --- | --- | --- |
| feature | `--proposal <PRP-ID> --objectives-file <步骤 2 确认文件>` | 不传 `--name`；CLI 从 PRP 文件名取出 slug |
| bugfix | `--bug <Bug-ID>` | 不传 `--name`；CLI 用该 ID 作为分支名 |
| release | `--version <semver> --objectives-file <步骤 2 确认文件>` | — |
| hotfix | `--version <semver>` | 不传 `--objectives-file` |

- 将步骤 3 确认的 roster 传给 CLI，不得改写已确认值：
  - 选用 named 时传 `--roster`。
  - 人数以 `--qa`、`--dev`、`--reviewers` 传入。
  - 策略以 `--qa-strategy`、`--dev-strategy`、`--review-strategy` 传入。
  - 有某 intent 的 model 时传对应
    `--write-tests-model` / `--implement-model` / `--code-review-model`。
- CLI 仍把一侧为 0 另一侧 ≥1 的 0 抬成 1；步骤 3 展示的须是抬成后的值。
- 未带的 `--*-model` 不写入 roster.models 对应键。
- `--roster` 只展开为人数与策略，不写入 delivery.json。
- CLI 要求 clean，且本地基线分支存在；不 fetch、不要求 origin、不 push。
- feature/bugfix/release 从本地 develop 创建，hotfix 从本地 master 创建。
- 本地已有同名分支则失败，不检查远端。
- 始终从基线在仓库同级 `<repo-name>-worktrees/<worktree-name>` 建立 worktree：
  - 路径等于分支名，`/` 为嵌套目录。
  - 不在当前目录开分支、不抢占当前 checkout。
- roster ≥1 时按人数建立 `qa/<owner>`、`dev/<owner>`，
  第 2 路起为 `qa/2/<owner>`、`dev/2/<owner>`；`0,0` 只建 owner。
- 成功 JSON 含 `worktree`（owner）、冻结后的 `roster` 与 `roles.qa` / `roles.dev` 列表。
- 创建中失败时 CLI 自动回滚本次已建的全部 worktree 与分支，Agent 不再手工拆除。

验收：检查、本地分支与实际工作目录。

异常与交接：

- 创建前检查失败时不创建分支并报告 finding；创建中失败时 CLI 已回滚，报告并停止。
- 不推送，不设置 upstream。
- CLI 在本地 Git config 中：
  - 以 `branch.<完整分支名>.mdf-start-commit` 固定起点完整 hash，供 bugfix/hotfix code-review 使用。
  - 以 `branch.<owner>.mdf-roster` 冻结人数与策略。
  - 删除分支时该配置随分支删除，不设置 upstream。
- 阶段材料：
  - feature 与 release 始终在 owner 写入 `changes/unreleased/<slug>/delivery.json`
    （含 roster）及 `objectives.md` 并提交。
  - roster ≥1 的 bugfix/hotfix 写入 `delivery.json`（含 roster），不写 objectives（由 design 补写）。
  - roster `0,0` 的 bugfix/hotfix 不创建阶段材料；hotfix 的 objectives.md 由 deliver 在开发前写入。
  - bugfix 的 named suite 关联由 deliver 的 Verify 阶段写入，本步不写。
- roster ≥1 时后续 write-tests / implement 使用 `roles` 列表中的路径。
- 创建成功进入 5，本步不结束。

<a id="s5"></a>

**切换**

目标固定为步骤 4 JSON 的 owner：`worktree` 绝对路径与 `branch` 完整分支名。

- qa/dev 不在本步切换。
- 按 `references/common.md` 的「切换工作区」规则判定当前 agent 并切到该路径与分支。
- 向用户给出应切到的绝对路径与分支名。
- 未切到则留在 5，重复对应指引，不拆除已建 worktree 与分支。
- 独立调用通过后结束，由用户手动触发 design 或通过 next 委托。
- deliver 内部委托时返回调用方。
