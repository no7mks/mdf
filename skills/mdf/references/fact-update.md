# Fact Update

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check and scope                │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 仓库已 ready 且范围明确
┌──────────────────────────────────┐
│ 2 Update                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Audit                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止并报告]
```

## 工作流（唯一执行契约）

读取 `references/common.md` 与 `references/repository-contract.md`；
步骤 3 读取并内部执行 `references/fact-audit.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 脚本 | 运行 doctor 检查初始化状态，确定事实与实现范围 | doctor、调用方、路径 | 2 | 写入前停止并报告 |
| 2 | 同步 | 约束 | 仅同步受影响事实及 evidence；独立调用按公共规则提交 | 事实 diff、适用提交 | 3 | 停止并报告 |
| 3 | 审阅 | 约束 | 委托 fact audit；按变更验证；feature finish 记录 gate | 审阅、验证、适用 gate | 结束 | 停止并报告 |

## 术语与数据结构

### 范围与写入边界

<a id="s1"></a>

**入口**

任何写入或提交前运行 `doctor --repo "$REPO_ROOT"`，核对命令成功且结果包含
`is_git_root: true`、`initialized: true`、`state: ready`。独立调用与 finish 委托均须满足；
未初始化、initializing 或 manifest 无法读取时提示 `$mdf init`，不写入、不提交；
工具失败或目标边界不符时报告并停止。
本步骤检查初始化状态，不将 `normal_workflows_allowed: true` 作为前置条件；
写入分支按 `common.md` 的归属规则检查；`branch.invalid` 不作为分支归属判断的替代。
已有 findings 如实记录，事实及 evidence 问题由步骤 2–3 按范围处理，
其他超出本次范围的问题报告后停止，不借同步入口修改无关对象或配置。

支持用户独立调用；也由 finish 在前段委托。独立调用不要求交付分支或阶段记录，不触发交付。
独立调用可在当前工作相关的 feature、bugfix、release 或 hotfix 分支同步事实；
在途 feature 时只在 owner 工作，cwd 为 qa/dev 则切回 owner。
无关的独立维护在 develop 完成，不在 master 写入。
独立调用基于用户范围和当前实现确定更新面；finish 调用采用固定起点到 HEAD 的精确范围。

验收：doctor 结果、调用方类型、事实与实现范围。

异常与交接：未初始化或范围不明时写入前停止并报告。

<a id="s2"></a>

**同步**

只更新受影响的当前事实及 evidence；不修改 PRP、Bug、Change、objectives 或 design 的意图。
不为满足形式制造无关文档，不把计划写为当前事实。实现有问题时报告，不用文案掩盖。
独立调用按公共规则主动提交本次事实改动；finish 委托时由调用方统一提交。
尚未完成审阅时准确说明提交状态，不将提交等同于审阅通过。

验收：事实 diff、适用提交。

异常与交接：写入失败保留现场，停止并报告。

### 审阅与验证证据

<a id="s3"></a>

**审阅**

内部委托 fact audit 做双向只读审阅与 full validation；通过前不得声称事实同步完成。
feature finish 调用时执行受影响验证，运行
`delivery record --stage fact-update --summary <本次事实审阅确认与验证证据>`。
只改事实文档不机械重跑全部业务验证；实现、测试或 verification 改变必须重跑
当前交付所需 suite。

验收：fact audit 通过、验证结果、feature finish 委托时的 fact-update gate。

异常与交接：fact audit 未通过或 gate 记录失败时停止并报告，不声称事实同步完成。
