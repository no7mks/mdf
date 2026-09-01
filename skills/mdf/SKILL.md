---
name: mdf
description: >-
  Mars Development Flow 的唯一入口。用户显式使用 $mdf、$mdf doc、$mdf codewiki 或
  $mdf jot promote 管理仓库文档、下一步规划、外部输入、CodeWiki、随手记录、审计、
  收口、归档或逐题澄清。
---

# Mars Development Flow

MDF 是面向 Git 仓库的版本化文档与交付流程，管理`当前事实文档`、ADR、调研、
Proposal、Bug 与 Change；`manifest` 约束`validation`和发布状态。它不替代任务管理，
将调研、已确认决策与`当前事实文档`分开，避免把候选方案误作已实现行为。
从初始化到归档，仓库内 Markdown 与 `manifest` 留下可验证的演进记录；绝不自动 commit。

## 选择树

```text
$mdf <调用>
├─ 裸调用、裸 doc/codewiki、未知调用 → 仅显示帮助
├─ init | intake | next [方向] | start | finish | audit | grill <议题>
│  └─ 读取 intents/<intent>.md
├─ doc create | review | archive → 读取对应 doc-<action>.md
├─ codewiki generate | update → 读取对应 codewiki-<action>.md
└─ jot | jot promote → 读取 intents/jot.md
```

## 工作流（唯一执行契约）

1. **约束**；只接受上树所列的显式调用；不得因缺文档、代码/测试状态或对话上下文
   隐式选择 intent；证据：完整、非空的调用；通过 → 2；失败 → 仅展示意图表与调用示例，
   不读取 intent、不检查仓库、不写入。
2. **脚本**；解析本文件绝对路径为 `MDF_ROOT`，确认 `scripts/mdf.py`，运行
   `python3 "$MDF_ROOT/scripts/mdf.py" info`；证据：三个版本均为数字 `2`；
   通过 → 3；失败 → 停止，不得模拟 CLI。
3. **约束**；完整读取选择树指定的 intent，并只按其按需读取说明读取公共引用；
   证据：已读取材料与其流程结果；通过 → 执行 intent；失败 → 停止并报告缺失材料。

调用示例包含 `intake`、`next [方向]`、`codewiki generate`、`codewiki update`、
`doc create`、`doc review`、`doc archive`、`jot`、`jot promote` 与
`grill <议题>`；裸 `$mdf` 只显示帮助。
对应文件为 `intents/intake.md`、`intents/next.md`、`intents/doc-create.md`、
`intents/doc-review.md`、`intents/doc-archive.md`、
`intents/codewiki-generate.md`、`intents/codewiki-update.md` 与
`intents/jot.md`。
CLI 形式为 `python3 "$MDF_ROOT/scripts/mdf.py" <command>`。

## 术语与数据结构

| 材料 | 位置 | 用途 |
| --- | --- | --- |
| 意图 | `intents/` | 定义用户意图的流程 |
| 公共契约 | `references/` | 定义目录、对象与 CodeWiki 契约 |
| 模板 | `assets/` | 供 intent 写入仓库产出物 |
| 确定性 CLI | `scripts/` | 由 intent 调用，不等同于用户意图 |

`$mdf <intent>`、`$mdf doc <action>`、`$mdf codewiki <action>` 与
`$mdf jot promote` 是用户入口；CLI command 由 intent 内部使用，不要求一一对应。
CLI 统一解析目标 Git 根，不假设当前目录就是目标仓库。
上述材料均不是可单独调用的 Skill。
