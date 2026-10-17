# 人工 feature 续办

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check delivery                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 身份或清单不符 ────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Select step                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 人工工作未勾 ────→ [交接用户并返回调用方]
                 ├──── 无剩余清单项 ────→ [返回调用方核验实际收口]
                 ├──── 前置未完成 ──────→ [停止并报告]
                 │
                 ▼ 可执行阶段已确定
┌──────────────────────────────────┐
│ 3 Delegate                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败或待确认 ────→ [按原 intent 交接]
                 └──── 阶段完成 ────────→ [返回调用方]
```

## 工作流（唯一执行契约）

仅 next / deliver 在 `delivery.json` 的 `manual` 为 true 时内部执行本工作流。
start 与各阶段 intent 只读取下文对应条款，不执行本续办工作流。
读取 `references/common.md`；当前会话已完整读取则复用。
next 在 Resume 内执行本表；deliver 在 Select 内执行 1–2，再在 Execute 内执行 3。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check delivery | 脚本 | 运行 delivery status；核对身份与六项清单 | 身份、roster、objectives | 2 | 停止并报告 |
| 2 | Select step | 约束 | 检查人工工作并选型 | 勾选、前置 | 阶段 3；无剩余返回 | 人工未勾交接；不符停止 |
| 3 | Delegate | 约束 | 按阶段表执行一个原 intent 并交接 | 原 intent 产物与勾选 | 返回调用方 | 按原 intent 交接 |

## 术语与数据结构

### 身份与启动

`$mdf start --manual` 按 feature 处理，不绑定 PRP；`delivery.json` 写入 `manual: true`。
本页规定人工 feature 的主线；普通交付的 design、开发与 converge 规则不适用。

- start 通过 clarify 确认工作范围及 slug；独立调用先询问再建议，deliver 按其 confidence 策略裁定。
- 从 develop 创建 `feature/<slug>` 与独立 owner worktree；roster 固定为 `0,0,1`。
- objectives 使用 `assets/templates/manual-objectives.md`。
  - 顺序：start → 人工工作 → code-review → verify smoke → fact update → close-out。
- start 自勾 start；人工工作仅由用户显式勾选，Agent 不得代勾。
  - 用户可要求 Agent 介入实现与测试；介入不代表人工工作已完成。
  - next / deliver 在人工工作未勾时交接给用户；所有模式同样不得代勾或越过。
  - 用户显式勾选后，由 next 单步续办或 deliver 串联剩余阶段。
- code-review 用 1 个 reviewer；前置为人工工作已勾，不要求 converge。
- verify smoke 执行 feature 的 branch 验证（lint/build/quick/smoke），
  写入 `verification-report.json`；通过后自勾 verify smoke。
- fact update 直接对齐当前事实，沿用其内部审阅与验证，通过后自勾 fact update。
  - deliver 的 until 排除内部 fact audit 时，fact update 返回截止点与未完成步骤，不代勾 fact update。
  - 进入前按 [pre-gitflow-finish](pre-gitflow-finish.md) 执行可选 hook；仅文档继续，
    其他改动先补 code-review 与 verify smoke；失败仅汇报，续办不重跑。
- close-out 核对上述前置项及报告；不要求 design、converge 或独立 fact audit 项。
  - Change 的 `proposals: []`；无 PRP 状态更新。
  - 沿用 feature 的 no-ff 合入 develop、源分支删除及 worktree 保留规则。

### 续办与验收

步骤 1 调用 `mdf.py delivery status --repo <owner>`，核对：

- `manual: true`、`feature/<slug>` 与 `needs_design: false`。
- 无 proposal，roster 为 `0,0,1`。
objectives 六项须与模板同序且没有缺项；不符则报告具体差异并停止。

步骤 2 先核对 start 已勾；未勾或人工工作勾选来源不明时停止并询问。
人工工作未勾时返回用户交接，不委托开发，也不自动勾选。
人工工作已勾后，按以下阶段表选择首个未勾项；各项前置必须已勾。

| 清单项 | 委托 intent | 完成证据 |
| --- | --- | --- |
| code-review | `references/code-review.md` | 1 人审查终稿、勾选与提交 |
| verify smoke | `references/verify.md`，branch scope | 通过的 branch 报告、勾选与提交 |
| fact update | 先可选 hook，再 `references/fact-update.md` | 适用补审补测、事实同步、内部审阅、勾选与提交 |
| close-out | `references/close-out.md` | Change、实际 Gitflow 结果 |

步骤 3 完整读取所选 intent 后执行；不同时委托多个阶段。
next 完成一个阶段后结束；deliver 返回 Select，继续选下一阶段。
deliver 委托时先核 until 截止点；只执行边界内的当前 intent，各项 decision 按其 confidence 策略裁定。
没有剩余清单项时，调用方仍须核验实际合并结果，不凭清单全勾宣称交付完成。
