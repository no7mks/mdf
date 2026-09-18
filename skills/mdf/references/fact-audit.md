# Fact Audit

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve scope                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Audit CLI                      │
└────────────────┬─────────────────┘
                 │
                 ├──── migrate 且仅 initializing ────→ 3 Review facts
                 ├──── 其他失败或缺失 ───────────────→ [停止]
                 │
                 ▼ CLI 成功
┌──────────────────────────────────┐
│ 3 Review facts                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 无法完成复核 ────→ [停止]
                 │
                 ▼ 通过（含已记录发现）
┌──────────────────────────────────┐
│ 4 Review coverage                │
└────────────────┬─────────────────┘
                 │
                 ├──── 无法完成复核 ────→ [停止]
                 │
                 ▼ 通过（含已记录发现）
┌──────────────────────────────────┐
│ 5 Review warnings                │
└────────────────┬─────────────────┘
                 │
                 ├──── 无法完成审阅 ────→ [停止]
                 │
                 ▼ 通过（含未确认项记录）
┌──────────────────────────────────┐
│ 6 Validate                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 7 Confirm review                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ────────────────→ [审阅通过]
                 ├──── 未通过且独立调用 ────→ [报告未通过并结束]
                 └──── 未通过且内部委托 ────→ [返回未通过，调用方走失败分支]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/common.md` 与 `references/repository-contract.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 范围 | 约束 | 确认调用方、状态与 `--scope`（branch/full/paths） | 类型、scope、两类范围 | 2 | 停止 |
| 2 | 映射 | 脚本 | 按 scope 运行 fact-audit CLI | 映射、体积、findings | 3 | migrate 仅 initializing 则 3；其他停止 |
| 3 | 事实 | 约束 | 逐份核对事实陈述及 evidence，按加载质量清单审阅结构 | 事实复核、语义发现 | 4 | 无法复核则停止 |
| 4 | 覆盖 | 约束 | 从实现反查用户与系统各面的文档覆盖 | 覆盖、遗漏与错误 | 5 | 无法复核则停止 |
| 5 | 警告 | 约束 | 逐条审阅 warning：未引用实现须用户确认，`size.soft` 记为待拆 | 逐条处置 | 6 | 无法审阅则停止 |
| 6 | 校验 | 脚本 | 运行 `validate --scope full`，不运行验证命令 | validation findings | 7 | 停止 |
| 7 | 确认 | 约束 | 报告发现并取得当场确认 | 摘要、当场确认 | 审阅通过 | 报告未通过；独立结束，委托返回 |

## 术语与数据结构

### 范围与确定性映射

<a id="s1"></a>

**范围**

它只读：不写入、移动、提交、生成持久报告或执行 `verification.commands`。

`--scope` 三选一，与 fact update 共用：

- `branch`：独立调用默认。交付分支以 `delivery.json` 的 `start_commit` 为 `--base`；
  否则 CLI 取 `merge-base develop HEAD`。范围是该起点以来改动的实现文件、改动到的
  事实页，以及 evidence 引用这些实现的事实页；同时检查改动到的入口页体积。
- `full`：全部当前事实、实现面、入口根文档、ADR 与工作对象体积。
- `paths`：调用方给出精确实现/文档路径；finish 与 fact update 委托用此形式。

确定类型和状态：fact update 委托时使用其明确范围，允许审阅调用方的同次写入；
direct 调用 manifest 必须 `ready`；migrate 为 `full`、允许 `initializing`；
finish 的 release 为 `full`，其他分支为 `paths` 范围审阅，不得改用 `full`。
审阅不要求 clean，不替调用方提交；未提交内容仍须满足 evidence 与 full validation 契约。

验收：调用方、scope 与范围。

<a id="s2"></a>

**映射**

调用 `fact-audit --scope <scope>`；`branch` 可带 `--base`，`paths` 带精确路径，
`full` 不带路径。CLI 同时按 `repository-contract.md` 的体积表检查：`size.hard`
是 finding，`size.soft` 是 warning。

验收：范围、文档—`evidence` 映射、ignore 匹配、体积、warnings、确定性 findings。

通过条件：CLI 成功，或 migrate 调用时返回结构化结果且 findings 仅有
`manifest.initializing`；后一种即使退出码为 2、ok 为 false 也继续审阅。
异常与交接：其他调用失败或确定性 finding 时停止；不得把解析失败当作初始化豁免。

### 双向复核与确认

<a id="s3"></a>

**事实**

从文档到实现执行`事实复核`：复核范围内每份当前事实文档、陈述和 `evidence`。
范围内未复核的文档逐份记录未触及理由，供步骤 7 报告。

同时按加载质量清单审阅范围内文档结构（`full` 覆盖 `docs/**` 与根文档），发现
计入语义 finding：

- 入口不过载：`README.md`、`PROJECT.md`、`AGENTS.md` 不复述事实页已记载的可观察
  契约；`docs/README.md` 是任务地图，当前事实排在决策与工作记录之前，不链接空目录，
  按任务只打开一份页面。
- 路由页只路由：`system/overview.md`、`user-guide/README.md`、切面 `index.md`
  不复述叶子契约，不集中承担 evidence。
- 唯一归属：同一可观察契约只在一页；其他页只链接。对外能力在 `user-guide`，
  内部结构与仍生效约束在 `system/architecture`，内部契约在 `system/interfaces`。
- 主题叶按主题拆：一页混多个主题、或该拆未拆（含 `size.hard`/`size.soft`）记为
  结构 finding，修复方向是拆页或下沉，不是压缩措辞。
- 读者分离：`user-guide` 只写使用者可观察的行为；维护者材料不混入。
- ADR：`docs/context/adr/` 不复述当前结构；仍生效约束若只写在 ADR 而
  `system/architecture` 缺失，记为 finding。ADR 不按实现对齐。
- 工作对象与调研：Proposal、Bug、Jot、research 未冒充当前事实、未被任务地图当成
  通读清单即可；不做拆页 refine。`docs/repowiki/` 不审、不改。
- `verification` 以可执行测试或命令为主，不把实现步骤写成源码 walkthrough。

验收：事实复核、加载质量发现、未触及理由。

异常与交接：记录语义 finding 后继续 4。

<a id="s4"></a>

**覆盖**

从实现到文档复核对外可观察行为（`user-guide`）、系统边界、架构、接口、数据与运维实现。

验收：未记录实现、过时/错误陈述、不可验证 evidence 与计划混写 findings。

异常与交接：记录语义 finding 后继续 5。

<a id="s5"></a>

**警告**

逐条审阅 CLI warning。

验收：未被 evidence 引用且未被 ignorelist 覆盖的实现文件及用户当场确认；
`size.soft` 逐条列为待拆建议，不要求当场确认，供 fact update 的结构阶段处理。

异常与交接：列入会话摘要后继续 6。

<a id="s6"></a>

**校验**

运行 `validate --repo "$REPO_ROOT" --scope full`（即 full validation），不运行验证命令；
migrate 只允许 `manifest.initializing` finding。

验收：validation findings。

异常与交接：报告并停止。

<a id="s7"></a>

**确认**

返回审阅类型、两类范围、映射、warnings、复核文档、语义/validation findings 与未触及理由。

验收：会话摘要和用户当场确认。

通过条件：无语义 finding（含结构 finding）、无 `size.hard`、无未确认 warning，且
validation 无阻断 finding 时通过；migrate 仅豁免 `manifest.initializing`。
`size.soft` 不阻断。该确认不跨调用复用。

异常与交接：存在其他 finding、未确认 warning 或未取得用户确认时，报告审阅未通过、
阻断原因与待确认项，不得称审阅通过。独立调用报告后结束；内部委托返回未通过结果，
由调用方进入既有失败分支，不得推进依赖审阅通过的步骤。修复、补充确认或重审由调用方
按其契约处理；fact audit 保持只读，不自行修复或自动重试。

Audit 不检查 Gitflow 分支、变更 diff、Proposal、Bug、Change、release 输入、closeout 或 merge 条件；这些属于
`$mdf finish` 的交付前检查。

### 审阅类型

- `全量审阅`（`--scope full`）：从文档和实现两个方向覆盖全部当前事实文档与实现面，
  并按加载质量清单覆盖 `docs/**` 与根文档。
- `范围审阅`（`--scope branch` 或 `paths`）：从文档和实现两个方向覆盖起点以来或
  调用方给定的实现与文档范围；结构检查只及范围内页面与改动到的入口页。
