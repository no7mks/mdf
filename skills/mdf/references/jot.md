# Jot

`$mdf jot` 追加一条 Jot；`$mdf jot promote` 提升一条既有 Jot；不接受其他子动作。

## 选择树

```text
┌──────────────────────────────────┐
│ 1 Check entry                    │
└────────────────┬─────────────────┘
                 │
                 ├──── doctor 通过且 jot promote ────→ 4 Select jot
                 ├──── doctor 失败 ────→ [停止]
                 │
                 ▼ doctor 通过且 jot
┌──────────────────────────────────┐
│ 2 Read input                     │
└────────────────┬─────────────────┘
                 │
                 ├──── 需澄清或消歧 ────→ 2 Read input
                 │
                 ▼ 输入唯一且完整
┌──────────────────────────────────┐
│ 3 Append                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ────→ [结束]
                 ├──── 失败/缺失 ────→ [保留现场，停止]

┌──────────────────────────────────┐
│ 4 Select jot                     │
└────────────────┬─────────────────┘
                 │
                 ├──── 需澄清或消歧 ────→ 4 Select jot
                 │
                 ▼ 输入唯一且完整
┌──────────────────────────────────┐
│ 5 Clarify                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留 Jot，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 6 Confirm                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留 Jot，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 7 Create object                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留两者，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 8 Promote                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ────→ [交接并结束]
                 ├──── 失败/缺失 ────→ [保留现场，停止]
```

## 工作流（唯一执行契约）

完整读取 `references/common.md`、`references/clarify.md`、 `references/repository-contract.md` 与
`references/object-contract.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 脚本 | [运行 doctor 并分流](#s1) | 允许正常流程 | 追加 2；提升 4 | 停止 |
| 2 | 内容 | 约束 | [获取完整原文](#s2) | 完整输入 | 3 | 留在 2 询问 |
| 3 | 追加 | 脚本 | [写 marker 并校验](#s3) | 条目、diff | 结束 | 保留现场，停止 |
| 4 | 选择 | 约束 | [读取唯一 Jot](#s4) | ID 与原文 | 5 | 留在 4 消歧 |
| 5 | 澄清 | 约束 | [查证并内部 clarify](#s5) | 完整草稿 | 6 | 保留 Jot，停止 |
| 6 | 确认 | 约束 | [展示草稿边界](#s6) | 用户确认 | 7 | 保留 Jot，停止 |
| 7 | 创建 | 脚本 | [写对象并首次校验](#s7) | 对象、校验结果 | 8 | 保留两者，停止 |
| 8 | 提升 | 脚本 | [转状态并移除 Jot](#s8) | 两次校验、diff | 交接并结束 | 保留现场，停止 |

## 术语与数据结构

### 执行约束

下列明细补充表中操作、证据与异常处理；步骤顺序和跳转只由上表规定。

<a id="s1"></a>

**入口**

解析 `REPO_ROOT` 并运行 `doctor`。

验收：`normal_workflows_allowed: true`。

通过条件：按调用进入 2 或 4。异常与交接：manifest 未就绪时提示 `$mdf init`，其他 findings 报告后停止。
同次仅处理一个 Jot，且保留其原文。

<a id="s2"></a>

**内容**

仅对裸 `$mdf jot` 要求用户提供内容。

验收：完整输入。

异常与交接：一次只问一个问题。内容可为任何未定性信息，不要求预判类型、优先级或可行性。

<a id="s3"></a>

**追加**

调用 `make-jot-id`、生成简短标题、在 `JOTS.md` 末尾追加完整 marker 条目， 保留原始含义和细节，再运行
`targeted validation`。

验收：新增条目和 diff。

异常与交接：保留现场并报告 findings。

<a id="s4"></a>

**选择**

仅对 `$mdf jot promote` 要求一个既有 `jot-` ID，读取完整 marker。

验收：唯一条目与其正文。

异常与交接：一次只问一个消歧问题。

<a id="s5"></a>

**澄清**

先查仓库证据，使用内部 clarify intent 按轮次将正文收敛为 Proposal 或 Bug；
Proposal 收敛 Problem、Desired Outcome、Scope、可验证 Acceptance Criteria；
Bug 收敛 Observed/Expected Behavior、Reproduction、Impact、 Regression Evidence Required、 `found_in`
与 active severity。

验收：完整 draft。

异常与交接：停止，不得改写 Jot。

<a id="s6"></a>

**确认**

展示 draft、确认事实与排除范围，并要求用户明确确认。

验收：确认。

异常与交接：停止，保留 Jot。

<a id="s7"></a>

**创建**

提议并确认英文 ASCII kebab-case slug；按对象类型 proposal 或 bug， 调用 `make-id --type <type> --slug <slug>`；
Proposal 写为 `draft`，Bug 写为 `open`，运行 `targeted validation`。

验收：新对象与首次 validation。

异常与交接：保留新对象、原 Jot 与现场，并报告 findings。

<a id="s8"></a>

**提升**

Proposal 转为 `ready`；Bug 保持 `open`。删除选中 Jot marker， 再运行 `targeted validation`。

验收：两个文件完整 diff 与两次验证。

异常与交接：保留现场并报告 findings。 成功时将本次创建与移除作为同一个独立 commit 提交。
