# Intake

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
│ 2 Resolve source                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 需澄清或消歧 ────→ 2 Resolve source
                 │
                 ▼ 输入唯一且完整
┌──────────────────────────────────┐
│ 3 Classify                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 无法判定 ────→ 2 Resolve source
                 │
                 ▼ 分类明确
┌──────────────────────────────────┐
│ 4 Clarify                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [不写对象，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 5 Confirm list                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 来源采用范围变化 ────────→ 2 Resolve source
                 ├──── 对象事实或边界需澄清 ────→ 4 Clarify
                 │
                 ▼ 用户确认清单
┌──────────────────────────────────┐
│ 6 Create objects                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留现场，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 7 Report                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/common.md`、`references/repository-contract.md` 与
`references/object-contract.md`。
步骤 4 读取并内部执行 `references/clarify.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 脚本 | 运行 `doctor`，核对允许正常流程 | doctor 结构化结果 | 2 | 停止 |
| 2 | 来源 | 约束 | 确认一次性来源及采用范围；逐题消歧 | 来源、已确认范围 | 3 | 等待澄清，2 |
| 3 | 分类 | 脚本 | 用 `list` 查重，依证据区分偏差与意图，确定对象边界 | list 结果、对象清单 | 4 | 回到 2 |
| 4 | 澄清 | 约束 | 内部 clarify 补齐各 Proposal/Bug 必填事实 | 完整必填事实 | 5 | 不写对象，停止 |
| 5 | 确认 | 约束 | 展示对象、边界、排除项和直接依赖并确认 | 用户明确确认的清单 | 6 | 来源 2；事实 4 |
| 6 | 创建 | 脚本 | 确认 slug，生成 ID、写初始对象、校验回读 | 零 finding、对象与 diff | 7 | 保留现场，停止 |
| 7 | 报告 | 约束 | 报告对象、范围、依赖和后续显式入口 | 结果摘要 | 结束 | 停止 |

## 术语与数据结构

### 入口与来源

<a id="s1"></a>

**入口**

解析 `REPO_ROOT` 并运行 `doctor`。

验收：`normal_workflows_allowed: true`。

异常与交接：manifest 未就绪时提示 `$mdf init`，其他 findings 报告后停止。

<a id="s2"></a>

**来源**

接收一句话、当前聊天上下文或外部文档为一次性来源；一次只问一个问题， 确认范围、关键事实与取舍；
除非用户明确要求保留，不得复制、归档或链接到仓库。

验收：确认的来源采用范围。

### 对象分类与确认

<a id="s3"></a>

**分类**

先运行 `list --repo "$REPO_ROOT"` 取得 active Proposal 与 Bug 的 `id`、`title`、`status`，
对照来源查重；命中既有对象时不新建，改为提示 `$mdf prp review` 或在既有 Bug 中补充，
不逐篇翻阅 `docs/proposals/` 与 `docs/bugs/`。
从来源和仓库证据判定对象类型、数量与独立交付边界；偏差建 Bug， 待实现意图建一个或多个 Proposal。
优先拆成尽可能小的 Proposal，以依赖满足后能独立实现、验收和合入为下限。
能分开验收的结果优先拆开；不按文件或开发步骤机械拆分，不扩张来源范围。
已足够小的交付单元无需继续拆分。

验收：对象清单。

异常与交接：回到 2。

<a id="s4"></a>

**澄清**

使用内部 clarify intent 按轮次澄清成稿必要事实；
Proposal 收敛 Problem、 Desired Outcome、Scope、可验证 Acceptance Criteria；
Bug 收敛 Observed/Expected Behavior、Reproduction、Impact、Regression Evidence Required、`found_in`
与 active severity。

验收：完整必填事实。

异常与交接：必填事实仍无法确认时停止，不得写入任何对象。

<a id="s5"></a>

**确认**

展示对象清单、边界、排除范围、Proposal 依赖；`depends_on`
仅列直接依赖的 draft、ready 或 implemented/released Proposal ID，
以及需要等待整阶段完成时的已有 milestone 值；候选 ID 与 milestone 取自步骤 3 的 `list` 输出。
逐条说明需要上游提供的结果；优先顺序不能作为依赖依据。
同属一个阶段不能写成对其中单个 PRP 的依赖。
可建议 milestone 分组，由用户决定是否采用；不默认一次 intake 对应一个 milestone，
不自动把最先实施的一两个 PRP 标为 MVP。有归属时展示并确认 `milestone`，无归属不强求补齐。

验收：只有用户明确确认清单才继续。

异常与交接：来源采用范围变化时回到 2；对象必填事实或边界需澄清时回到 4。

### 对象写入与交接

<a id="s6"></a>

**创建**

为每项提议并确认英文 ASCII kebab-case slug，按类型 proposal 或 bug 使用 `make-id --type <type> --slug <slug>`
生成 ID 与规范化文件名，并以模板写入 `docs/proposals/` 或 `docs/bugs/`；
Proposal 初始状态为 `draft`，Bug 初始状态为 `open`。
Proposal 仅在已确认阶段归属时写入非空字符串 `milestone`；否则省略字段，不写 `null`。

全部对象写入后运行 `validate --repo "$REPO_ROOT" --scope targeted`，
回读对象并对照模板、确认清单与完整 diff，核对 schema、必填章节、初始状态和依赖。

验收：所有新建对象、校验退出 0 且零 finding、回读结果与 diff。

异常与交接：校验、回读或核对失败时停止并保留现场，报告 findings 与实际已写对象，
不得宣称创建验收通过，不进入步骤 7 的成功报告。

<a id="s7"></a>

**报告**

展示新建对象、确认事实、排除范围和依赖。

验收：会话摘要。

异常与交接：停止。Proposal 后续显式调用 `$mdf prp review`，经 draft targeted validation 后转为 `ready`；
Bug 创建后即为 `open`，不得关闭普通对象或填写 `released_in`/`fixed_in`。
