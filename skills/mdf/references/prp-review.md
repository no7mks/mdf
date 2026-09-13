# PRP Review

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check entry                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Select proposal                │
└────────────────┬─────────────────┘
                 │
                 ├──── 需澄清或消歧 ────→ 2 Select proposal
                 │
                 ▼ 输入唯一且完整
┌──────────────────────────────────┐
│ 3 Check state                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 已开工 ───────→ [保留对象，停止]
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 4 Clarify                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留 draft，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 5 Confirm                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留 draft，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 6 Validate and ready             │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [保留现场，停止]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/common.md`、`references/repository-contract.md` 与
`references/object-contract.md`。
步骤 4 读取并内部执行 `references/clarify.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 脚本 | 运行 `doctor`，核对允许正常流程 | doctor 结构化结果 | 2 | 停止 |
| 2 | 选择 | 脚本 | 按 ID 或路径确定唯一 PRP；未指定时用 `list` 列候选 | 唯一对象 | 3 | 留在 2 消歧 |
| 3 | 状态 | 脚本 | 判定未开工才转 draft | list 结果、状态检查 | 4 | 已开工保留对象；其他停止 |
| 4 | 澄清 | 约束 | 查仓库证据，内部 clarify 目标、范围与验收 | 完整 draft、证据 | 5 | 保留 draft，停止 |
| 5 | 确认 | 约束 | 展示 draft、事实、排除范围与 diff 并确认 | 用户明确确认 | 6 | 保留 draft，停止 |
| 6 | 就绪 | 脚本 | 先校验 draft，通过才写 ready 并回读 | 校验结果、回读状态 | 结束 | 保留现场，停止 |

## 术语与数据结构

### 入口与未开工检查

<a id="s1"></a>

**入口**

解析 `REPO_ROOT` 并运行 `doctor`。

验收：`normal_workflows_allowed: true`。

异常与交接：manifest 未就绪时提示 `$mdf init`，其他 findings 报告后停止。

<a id="s2"></a>

**选择**

一次只接受一个 Proposal 的 canonical `prp-` ID 或仓库相对路径。
用户未指定时运行 `list --repo "$REPO_ROOT" --type proposal --status draft --status ready`，
按输出的 `id`、`title`、`status`、`blocked_by` 与 `in_progress` 列出候选供用户选择；
不逐篇翻阅 `docs/proposals/`。

验收：唯一对象。

异常与交接：一次只问一个消歧问题。

<a id="s3"></a>

**状态**

released/rejected/replaced/implemented 或 archive Proposal 拒绝修改。
在修改状态或正文前，以 `list --repo "$REPO_ROOT" --type proposal` 输出中目标 PRP 的 `status`
与 `in_progress` 为准：`in_progress` 已覆盖当前 checkout 的 `changes/` 下全部
`delivery.json`，以及本地 `feature/*` 和 `origin/feature/*` 引用中的同类记录，
任一记录的 `proposal` 命中目标 ID 即为 `true`。
不能仅凭当前 checkout 没有开发材料或 `next` 未显示进行中，就判定未开工。
已开工时报告关联分支与材料位置，保留对象和交付基线并停止；本入口不修改已开工 PRP。
`list` 因记录损坏失败或目标不在输出中时同样在写入前停止，报告缺失证据。
仅 active draft/ready 且已确认未开工时继续；将既有 `ready` 转为 `draft`，
取消、暂停或未确认时保持 `draft`。

验收：原状态、检查过的引用与材料范围、未开工结论，以及写回后的 draft 状态。

### 草稿与确认

<a id="s4"></a>

**澄清**

先查仓库证据，使用内部 clarify intent 按轮次澄清 Problem、Desired Outcome、 Scope 与可验证 Acceptance Criteria。

验收：完整 draft。

异常与交接：保持 draft 并停止。

<a id="s5"></a>

**确认**

展示 draft、确认事实、排除范围和既有对象 diff。

验收：用户明确确认。

异常与交接：保持 draft，可提交并准确说明尚未确认的状态；取得确认后继续，无须仅因提交而重调。
只有用户明确确认才转 `ready`。

### 就绪条件

<a id="s6"></a>

**就绪**

先在 `draft` 状态运行 `targeted validation`，通过后转为 `ready`。

验收：validation 通过；写回后回读对象，确认状态为 `ready`。

异常与交接：保留 draft 和现场。不得关闭对象或填写 `released_in`。 写回失败时保留实际现场并停止，
不得声称已 ready。
