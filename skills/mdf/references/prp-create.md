# PRP Create

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
│ 2 Resolve proposal               │
└────────────────┬─────────────────┘
                 │
                 ├──── 命中既有对象 ────→ [停止并交接]
                 ├──── 需澄清或消歧 ────→ 2 Resolve proposal
                 │
                 ▼ 输入唯一且完整
┌──────────────────────────────────┐
│ 3 Clarify                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [不写对象，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 4 Confirm                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 取消或拒绝 ────────────→ [停止]
                 ├──── 输入对象或来源变化 ────→ 2 Resolve proposal
                 ├──── 既定对象需澄清 ────────→ 3 Clarify
                 │
                 ▼ 用户确认 draft
┌──────────────────────────────────┐
│ 5 Create draft                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留现场，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 6 Report                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/common.md`、`references/repository-contract.md` 与
`references/object-contract.md`。
步骤 3 读取并内部执行 `references/clarify.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 约束 | 运行 doctor 与 planning ensure，切换至 planning | doctor、工作区 | 2 | 未切换留 1；其他停止 |
| 2 | 对象 | 脚本 | 用 `list` 查重并确认单个 Proposal | list 结果、唯一对象 | 3 | 命中则停止；否则留 2 |
| 3 | 澄清 | 约束 | 内部 clarify 补齐目标、范围、验收与直接依赖 | 完整必填事实 | 4 | 不写对象，停止 |
| 4 | 确认 | 约束 | 展示边界、排除项与依赖，取得 draft 确认 | 用户明确确认 | 5 | 取消停止；来源 2；事实 3 |
| 5 | 创建 | 脚本 | 确认 slug，生成 ID、写 draft、校验并回读 | 零 finding、对象与 diff | 6 | 保留现场，停止 |
| 6 | 报告 | 约束 | 报告 draft、事实、排除项与后续评审入口 | 结果摘要、依赖 | 结束 | 停止 |

## 术语与数据结构

### 入口与输入

<a id="s1"></a>

**入口**

解析 `REPO_ROOT` 并运行 `doctor`。运行
`planning ensure --repo "$REPO_ROOT"`，按 `references/common.md` 的
「切换工作区」规则进入 JSON `worktree`（分支 `planning`），再重新解析目标根。

验收：`normal_workflows_allowed: true`，当前分支为 `planning`。

异常与交接：manifest 未就绪时提示 `$mdf init`，其他 findings 或尚未切到
planning 工作区时报告后停止或留在本步。

<a id="s2"></a>

**对象**

接收用户手动提供的单个 Proposal 事实；一次不得创建多个对象；一次只问一个问题，澄清范围、关键事实与取舍。
运行 `list --repo "$REPO_ROOT" --type proposal` 对照 `title` 与正文查重，命中既有 PRP 时不新建，
提示 `$mdf prp review`；该输出同时作为步骤 3、4 依赖候选与 milestone 值的来源，不逐篇翻阅 `docs/proposals/`。
外部想法、当前聊天上下文或外部文档必须显式调用 `$mdf intake`。

验收：确认的 Proposal 与采用范围。

异常与交接：命中既有 PRP 时停止并交接；范围不明时留在 2。

### 事实与确认

<a id="s3"></a>

**澄清**

使用内部 clarify intent 按轮次澄清 Problem、Desired Outcome、Scope、可验证 Acceptance Criteria 与直接依赖。

验收：完整必填事实。

异常与交接：必填事实仍无法确认时停止，不得写入任何对象。

<a id="s4"></a>

**确认**

展示 Proposal、边界、排除范围和依赖；`depends_on`
仅列直接依赖的 draft、 ready 或 implemented/released Proposal ID，
以及需要等待整阶段完成时的已有 milestone 值。
如有阶段归属，同时确认可选 `milestone`；无归属不要求补齐。

验收：只有用户明确确认 draft 才继续。

异常与交接：取消或拒绝则停止；输入对象或来源变化时回到 2；既定对象的事实、范围或验收需澄清时回到 3。

### 对象写入与交接

<a id="s5"></a>

**创建**

为 Proposal 提议并确认英文 ASCII kebab-case slug；须在 active Proposal 与 Bug
中唯一，且不得与对象 ID 同形。使用
`make-id --type proposal --repo "$REPO_ROOT" --slug` 按已有最大序号加一
生成 ID 与规范化文件名，并以模板写入 `docs/proposals/`，初始状态为 `draft`。
仅在已确认阶段归属时添加非空字符串 `milestone`；否则省略字段，不写 `null`。

写入后运行 `validate --repo "$REPO_ROOT" --scope targeted`，回读对象并对照模板、
确认事实与完整 diff，核对 schema、必填章节、`draft` 状态和依赖。

验收：draft Proposal、校验退出 0 且零 finding、回读结果与 diff。

异常与交接：校验、回读或核对失败时停止并保留现场，报告 findings 与实际已写对象，
不得宣称创建验收通过，不进入步骤 6 的成功报告。

<a id="s6"></a>

**报告**

展示 draft Proposal、确认事实、排除范围和依赖。

验收：会话摘要。

异常与交接：停止。后续显式调用 `$mdf prp review`，经 draft targeted validation 后转为 `ready`；
不得关闭普通对象或填写 `released_in`。
