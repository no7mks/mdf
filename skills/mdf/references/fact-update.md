# Fact Update

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check and scope                │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 仓库已 ready 且 scope 明确
┌──────────────────────────────────┐
│ 2 Align facts                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 事实与实现一致
┌──────────────────────────────────┐
│ 3 Audit                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 其他未通过 ────→ [停止并报告]
                 │
                 ▼ 通过或仅结构 finding
┌──────────────────────────────────┐
│ 4 Refine structure               │
└────────────────┬─────────────────┘
                 │
                 ├──── 有改写 ───────→ 3 Audit
                 ├──── 失败/缺失 ────→ [停止并报告]
                 └──── 无改写 ───────→ [记录 gate 并结束]
```

## 工作流（唯一执行契约）

读取 `references/common.md` 与 `references/repository-contract.md`；
步骤 3 读取并内部执行 `references/fact-audit.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check and scope | 脚本 | 运行 doctor，确定 scope 与范围 | doctor、调用方、scope、路径 | 2 | 写入前停止并报告 |
| 2 | Align facts | 约束 | 按实现同步范围内当前事实及 evidence | 事实 diff | 3 | 停止并报告 |
| 3 | Audit | 约束 | 委托 fact audit；按变更验证 | 审阅、验证 | 4 | 停止并报告 |
| 4 | Refine structure | 约束 | 只改范围内结构 finding 并记 gate | 结构 diff、gate | 改写回 3；否则结束 | 停止并报告 |

## 术语与数据结构

### 范围与写入边界

<a id="s1"></a>

**入口**

任何写入或提交前运行 `doctor --repo "$REPO_ROOT"`，核对命令成功且结果包含
`is_git_root: true`、`initialized: true`、`state: ready`。独立调用与 finish 委托均须满足；
未初始化、initializing 或 manifest 无法读取时提示 `$mdf init`，不写入、不提交；
`layout.migrate` 或 `manifest.schema` finding 提示 `$mdf migrate`，本 intent 不搬布局。
工具失败或目标边界不符时报告并停止。
本步骤检查初始化状态，不将 `normal_workflows_allowed: true` 作为前置条件；
写入分支按 `common.md` 的归属规则检查；`branch.invalid` 不作为分支归属判断的替代。
已有 findings 如实记录，事实及 evidence 问题由步骤 2–4 按范围处理，
其他超出本次范围的问题报告后停止，不借同步入口修改无关对象或配置。

`--scope` 与 fact audit 同义，三选一：

- `branch`：独立调用默认。交付分支以 `start_commit` 为起点，否则以 `develop` 的
  merge-base 为起点；范围是该起点以来实现改动该碰的事实页与被改到的路由链接，
  不是「分支上改过的 Markdown」。未改实现只想整理文档时显式用 `full`。
  finish release 的 `--base` 为上一正式发布的 master commit/tag（与
  code-review 同一左端点）；首次发布无上一版本时停止确认初始基线。
- `full`：知识面全树——`docs/user-guide/**`、`docs/system/**`、入口根文档、
  `docs/context/adr/` 的复述检查与全部体积。结构 finding 可全改。
- `paths`：调用方给出精确实现/文档路径。

finish 只能委托 `branch` 或等价 `paths`，不得改用 `full`；全库整理走显式
`$mdf fact update --scope full`。

支持用户独立调用；也由 finish 在前段委托。独立调用不要求交付分支或阶段记录，不触发交付。
独立调用可在当前工作相关的 feature、bugfix、release 或 hotfix 分支同步事实；
在途 feature 时只在 owner 工作，cwd 为 qa/dev 则切回 owner。
无关的独立维护在 develop 完成，不在 master 写入。
finish 调用采用固定起点到 HEAD 的精确范围：feature/bugfix/hotfix 为
start_commit，release 为上一正式发布。

验收：doctor 结果、调用方类型、scope、事实与实现范围。

异常与交接：未初始化或范围不明时写入前停止并报告。

<a id="s2"></a>

**对齐**

只更新范围内受影响的当前事实及 evidence；不修改 PRP、Bug、Change、objectives 或
design 的意图，不改 `docs/context/`、`docs/repowiki/`。
`user-guide` 只在对外可观察行为有变时改；`system/architecture` 只在内部结构或仍
生效约束有变时改。不为满足形式制造无关文档，不把计划写为当前事实。实现有问题时
报告，不用文案掩盖。本步不改结构。

验收：事实 diff。

异常与交接：写入失败保留现场，停止并报告。

### 审阅与结构

<a id="s3"></a>

**审阅**

内部委托 fact audit（同一 `--scope`）做双向只读审阅与 full validation；通过前不得
声称事实同步完成。feature finish 调用时执行受影响验证。只改事实文档不机械重跑全部
业务验证；实现、测试或 verification 改变必须重跑当前交付所需 suite。

审阅结果分三类：通过；仅剩结构 finding（加载质量清单、`size.hard` 待拆）；其他
未通过（事实错误、覆盖遗漏、validation 阻断）。

验收：fact audit 结论、验证结果。

异常与交接：其他未通过时停止并报告，不声称事实同步完成；仅结构 finding 进入 4。

<a id="s4"></a>

**结构**

只对步骤 3 记录的、且位于范围内的结构 finding 做最小改写：拆页或下沉到主题叶、
把复述改为链接、把只在 ADR 里的仍生效约束写入 `system/architecture` 并在 ADR
留链接、瘦身路由页。不改承诺的行为，不改范围外页面，不为「顺手」重排文档树。
有改写则回到 3 重审；无改写或重审通过后按公共规则提交，finish 委托时由调用方
统一提交。feature finish 委托时运行
`delivery record --stage fact-update --summary <本次事实审阅确认与验证证据>`。

验收：结构 diff、适用提交、feature finish 委托时的 fact-update gate。

异常与交接：写入失败保留现场；gate 记录失败时停止并报告，不声称事实同步完成。
