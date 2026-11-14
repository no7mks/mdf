# PRP Review

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check entry                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 未切换 ───────→ 1 Check entry
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
                 ├──── 已开工 ────────→ [保留对象，停止]
                 ├──── 失败/缺失 ─────→ [停止]
                 ├──── 续办 ready ────→ 5 Confirm
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 4 Clarify                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 需补稿 ───────→ 4 Clarify
                 ├──── 失败/缺失 ────→ [保留 draft，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 5 Confirm                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留文件，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 6 Validate and ready             │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ──────────────────────→ [结束]
                 ├──── 确认稿已变 ────────────────→ 5 Confirm
                 ├──── 校验失败 ──────────────────→ [保留文件，停止]
                 └──── 写回、提交或 land 失败 ────→ [报告实际状态，停止]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取以下契约：

- `references/common.md` 与 `references/repository-contract.md`。
- `references/object-contract.md`。

步骤 4 读取并内部执行 `references/clarify.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check entry | 脚本 | 运行 doctor 并进入项目记录写入分支 | doctor、工作区 | 2 | 未切换留 1；其他停止 |
| 2 | Select proposal | 脚本 | 按 ID 或路径确定唯一 PRP；未指定时用 `list` 列候选 | 唯一对象 | 3 | 留在 2 消歧 |
| 3 | Check state | 脚本 | 核对未开工及目标文件，再准备 draft | list 结果、状态检查 | 新评审与 draft 到 4；续办 ready 到 5 | 保留对象，报告后停止 |
| 4 | Clarify | 约束 | 查证并内部 clarify 目标、范围与验收 | 完整 draft、证据 | 5 | 需补稿留 4；其余保留 draft，停止 |
| 5 | Confirm | 约束 | 展示当前 Markdown 并确认 | 文件、摘要、用户确认 | 6 | 保留文件，停止 |
| 6 | Validate and ready | 脚本 | 校验、写入或续办 ready，再提交；gitflow 执行 land | ready、提交结果 | 结束 | 稿变回 5；其余报状态 |

## 术语与数据结构

### 入口

<a id="s1"></a>

**入口**

1. 解析 `REPO_ROOT` 并运行 `doctor`；先核对 `normal_workflows_allowed: true`。
   未通过时按下方异常规则停止。
2. 按 [项目记录](common.md#项目记录) 的模式矩阵准备写入位置。
   github-flow 的 trunk 使用 `pm prepare --repo "$REPO_ROOT" --for-prp-review`，允许 worktree 有未提交改动。
   续办 [pm PR 反馈](pr.md#pm-分支) 时使用已锁定 source 对应的临时 worktree。
3. 按 `references/common.md` 的「切换工作区」规则进入选定 worktree。
4. 再重新解析目标根。

验收：`normal_workflows_allowed: true`，当前分支符合写入归属。

异常与交接：manifest 未就绪时提示 `$mdf init`；`normal_workflows_allowed: false` 时报告
findings 后停止。尚未进入写入位置时留在本步。

<a id="s2"></a>

### 对象与写入检查

**选择**

- 一次只接受一个 Proposal 的 canonical `prp-` ID 或仓库相对路径。
- 用户未指定时运行 `list --repo "$REPO_ROOT" --type proposal --status draft --status ready`。
  - 按输出的 `id`、`title`、`status`、`blocked_by` 与 `in_progress` 列出候选供用户选择。
  - 不逐篇翻阅 `docs/proposals/`。

验收：唯一对象。

异常与交接：无法确定唯一对象时留在 2。

<a id="s3"></a>

**状态**

❌ released/rejected/replaced/implemented 或 archive Proposal 拒绝修改。

在修改状态或正文前，以 `list --repo "$REPO_ROOT" --type proposal` 输出中
目标 PRP 的 `status` 与 `in_progress` 为准：

- `in_progress` 已覆盖以下记录，任一记录的 `proposal` 命中目标 ID 即为 `true`：
  - 当前 checkout 的 `changes/` 下全部 `delivery.json`；
  - 本地 `feature/*` 和 `origin/feature/*` 引用中的同类记录。
- ⚠️ 不能仅凭当前 checkout 没有开发材料或 `tree` 未显示进行中，就判定未开工。

| 情形 | 处理 |
| --- | --- |
| 已开工 | 报告关联分支与材料位置，保留对象和交付基线并停止；本入口不修改已开工 PRP |
| `list` 因记录损坏失败或目标不在输出中 | 同样在写入前停止，报告缺失证据 |
| 新评审的 active draft/ready，已确认未开工 | 在当前写入位置继续；ready 用 `prp-review draft --repo "$REPO_ROOT" --proposal <PRP-ID>` 原位转为 draft |

- github-flow 在首次写入前执行 `prp-review prepare --repo "$REPO_ROOT" --proposal <PRP-ID>`。
  有未完成的 Git 操作或目标 PRP 已有未提交改动时，保留现场并报告。
- 恢复本次评审时，先核对目标文件的 diff 并确认可沿用本轮草稿。修改前核对未完成的 Git 操作；
  只读评审可以先进行。
- github-flow 续办已写入 `ready` 的评审时，保留该状态并进入步骤 5。

完成评审前取消或暂停时，保留当前稿件与状态。写回 ready 后遇到失败，按步骤 6 报告实际状态。

验收：原状态、未开工结论，以及当前 draft 或续办的 ready 状态。

### 草稿与确认

<a id="s4"></a>

**澄清**

先查仓库证据，使用内部 clarify intent 澄清 Problem、Desired Outcome、 Scope 与可验证 Acceptance Criteria。

验收：完整 draft。

- 在 Markdown draft 中写清事实依据、约束、依赖、设计取舍、风险与逐条验收方法。
- 对已有 PRP 附上本次 diff，供用户核对。

异常与交接：需要补稿时留在 4；其他失败保持 draft 并停止。

可选加速（见 `common.md`「Jev 可选加速」）：

- 时机：clarify 完成后、展示确认前；tool 可用时。
- 调用：`noul`（是否达 ready 质量），或 `score`
  （0=可确认 / 1=小补 / 2=须回澄清）。
- state：draft 与证据摘要。
- 采信「可确认」仅用于整理展示材料。
- ❌ 不替代步骤 5 用户确认，不得因 Jev 直接写 `ready`。
- 需补稿时留在步骤 4；完整 draft 才进入步骤 5。
  未采信时由主 Agent 按同一条件裁定。

<a id="s5"></a>

**确认**

1. 运行 `prp-review check --repo "$REPO_ROOT" --proposal <PRP-ID>`，记录返回的文件路径和 `sha256`。
2. 向用户展示该 Markdown 文件，确认事实、排除范围、取舍、验收方法及本次 diff。
3. 取得对该文件的明确确认。改稿后重新运行 `check`，展示改稿并确认。

验收：用户明确确认。

异常与交接：未确认则保留当前文件并停止。阶段提交不构成确认。
只有用户明确确认才转 `ready`。

### 就绪条件

<a id="s6"></a>

**就绪**

- 首次写入 `ready` 时，先在 `draft` 状态运行 `basic validation`。
- 通过后，用步骤 5 的摘要在原 Markdown 文件中写入 ready 状态。

```bash
python3 "$MDF_ROOT/scripts/mdf.py" prp-review ready --repo "$REPO_ROOT" --proposal <PRP-ID> --confirmed-sha256 <SHA256>
```

回读确认状态为 `ready` 后，gitflow 按步骤 1 的项目记录流程提交并 land。
github-flow（包含 `pm/*` 返工）用 `ready` 返回的 `sha256` 提交该文件。
续办 `ready` 稿时，用步骤 5 确认的 `ready` 摘要直接提交：

```bash
python3 "$MDF_ROOT/scripts/mdf.py" prp-review commit --repo "$REPO_ROOT" --proposal <PRP-ID> --ready-sha256 <SHA256> --message 'docs(pm): 完成 PRP 评审'
```

github-flow 的 `ready` 与 `commit` 均检查目标 PRP 上的暂存改动及未完成的 Git 操作。
直接调用提交命令，保留其余文件的暂存和未暂存状态。当前 PRP 已与 HEAD 一致时无需新提交。

验收：validation 通过，原路径上的 Markdown 文件状态为 `ready`，且评审稿已在 HEAD。

异常与交接：

- validation 失败：保留当前文件和状态，停止。
- `review_changed`：回步骤 5 展示当前 Markdown 并取得确认。
  github-flow 的 `check` 返回当前状态和摘要。若已是 `ready`，用重新确认的摘要直接重试 `commit`。
- github-flow 已写入 `ready` 但提交失败：修复失败原因，使用已确认的 `ready` 摘要重试 `commit`。
- 写回 `ready`、回读、提交或收口失败时保留现场，报告写回、提交及会话内已执行的合入状态。
- 不得关闭对象或填写 `released_in`。
