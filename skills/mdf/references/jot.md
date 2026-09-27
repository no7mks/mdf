# Jot

`$mdf jot` 追加一条 Jot；`$mdf jot promote` 提升一条既有 Jot；不接受其他子动作。
步骤 4–8 由步骤 1 的 promote 进入，不是步骤 3 的后续。

## 选择树

```text
┌──────────────────────────────────┐
│ 1 Check entry                    │
└────────────────┬─────────────────┘
                 │
                 ├──── doctor 通过且 jot promote ────→ 4 Select jot
                 ├──── 未知子动作 ───────────────────→ [停止]
                 ├──── doctor 失败 ──────────────────→ [停止]
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
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [保留现场，停止]

步骤 4 至 8 仅由步骤 1 的 jot promote 进入，不是步骤 3 的后续。

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
                 ├──── 通过 ────────────→ [交接并结束]
                 ├──── 首次校验失败 ────→ [保留现场，停止]
                 └──── 二次校验失败 ────→ [回滚到步骤 7 完成状态，停止]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/common.md`、`references/repository-contract.md` 与
`references/object-contract.md`。
仅提升的步骤 5 读取并内部执行 `references/clarify.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check entry | 脚本 | 运行 `doctor`；按追加或提升分流 | 允许正常流程 | 追加 2；提升 4 | 未知或 doctor 失败则停 |
| 2 | Read input | 约束 | 取得一条完整原文，不预判类型 | 完整输入 | 3 | 留在 2 询问 |
| 3 | Append | 脚本 | 生成 ID，追加完整 marker 并 targeted 校验 | 条目、校验、diff | 结束 | 保留现场，停止 |
| 4 | Select jot | 约束 | 按 jot-ID 读取唯一条目的完整 marker | 唯一 ID 与原文 | 5 | 留在 4 消歧 |
| 5 | Clarify | 约束 | 用 `list` 查重，内部 clarify 成 Proposal/Bug | 完整草稿、list 结果 | 6 | 保留 Jot，停止 |
| 6 | Confirm | 约束 | 展示草稿、事实及排除范围，取得明确确认 | 用户明确确认 | 7 | 保留 Jot，停止 |
| 7 | Create object | 脚本 | 确认 slug，生成 ID、写初始对象并首次校验 | 对象、首次校验 | 8 | 保留两者，停止 |
| 8 | Promote | 脚本 | 复验、提交；Proposal 再 land | 校验、diff、提交、land | 交接并结束 | 首次保留；二次回滚停止 |

## 术语与数据结构

### 入口与追加

<a id="s1"></a>

**入口**

解析 `REPO_ROOT` 并运行 `doctor`。

验收：`normal_workflows_allowed: true`。

通过条件：按调用进入 2 或 4。

异常与交接：

- 未知子动作停止。
- manifest 未就绪时提示 `$mdf init`，其他 findings 报告后停止。
- 同次仅处理一个 Jot，且保留其原文。

<a id="s2"></a>

**内容**

仅对裸 `$mdf jot` 要求用户提供内容。

验收：完整输入。

异常与交接：内容缺失时询问。内容可为任何未定性信息，不要求预判类型、优先级或可行性。

<a id="s3"></a>

**追加**

1. 调用 `make-jot-id`。
2. 从原文压缩一句短标题（不另写生成器）。
3. 在 `docs/JOTS.md` 末尾追加完整 marker 条目，保留原始含义和细节。
4. 再运行 `targeted validation`。

验收：新增条目和 diff。

异常与交接：保留现场并报告 findings。

### 提升输入与确认

<a id="s4"></a>

**选择**

仅对 `$mdf jot promote` 要求一个既有 `jot-` ID，读取完整 marker。

验收：唯一条目与其正文。

异常与交接：无法确定唯一条目时留在 4。

<a id="s5"></a>

**澄清**

1. 先运行 `list --repo "$REPO_ROOT"` 对照 active Proposal 与 Bug 的 `id`、`title`、`status` 查重。
   - 命中既有对象时停止提升并提示 `$mdf prp review` 或补充既有 Bug。
   - 不逐篇翻阅对象目录。
2. 再查仓库证据，使用内部 clarify intent 将正文收敛为 Proposal 或 Bug：

| 对象 | 收敛内容 |
| --- | --- |
| Proposal | Problem、Desired Outcome、Scope、可验证 Acceptance Criteria |
| Bug | Observed/Expected Behavior、Reproduction、Impact、Regression Evidence Required、`found_in` 与 active severity |

验收：完整 draft。

异常与交接：停止，不得改写 Jot。

<a id="s6"></a>

**确认**

展示 draft、确认事实与排除范围，并要求用户明确确认。

验收：确认。

异常与交接：停止，保留 Jot。

### 状态与同批提交

<a id="s7"></a>

**创建**

提议并确认英文 ASCII kebab-case slug；须在 active Proposal 与 Bug 中唯一，
且不得与对象 ID 同形。

- 提升为 Proposal 时：
  1. 先运行 `planning ensure`。
  2. 按 `references/common.md` 的「切换工作区」规则切换到 planning 工作区。
  3. 再调用 `make-id --type proposal --repo "$REPO_ROOT" --slug <slug>`。
- 提升为 Bug 时按 `common.md` 归属处理，调用 `make-id --type bug --slug <slug>`。

Proposal 写为 `draft`，Bug 写为 `open`，运行 `targeted validation`。

验收：新对象与首次 validation。

异常与交接：保留新对象、原 Jot 与现场，并报告 findings。

<a id="s8"></a>

**提升**

不重写对象。

1. 在步骤 7 已写入的 draft/open 上先运行 `targeted validation`。
2. 通过后 Proposal 转为 `ready`；Bug 保持 `open`。
3. 然后删除选中 Jot marker，再运行第二次 `targeted validation`。

第一次校验失败时尚未改动状态与 Jot，保留 draft/open 对象与原 Jot 并停止。

第二次校验失败时转状态与删 Jot 已落盘。此时按本 intent 恢复规则回滚到
步骤 7 完成状态（恢复 draft/open 状态与原 Jot marker），不提交。

验收：两个文件完整 diff 与两次验证。

异常与交接：

- 第一次失败保留两者，第二次失败先回滚再保留两者，均报告 findings。
- 成功时将本次创建与移除作为同一个独立 commit 提交。
- 提升为 Proposal 时再运行 `planning land --repo "$REPO_ROOT"` 合入 develop。
