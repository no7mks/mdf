---
name: mdf
description: >-
  管理 Git 仓库的版本化文档与交付流程：项目起步、初始化、已有项目迁移、规划、分诊、
  CodeWiki、随手记录、审计、收口、归档、帮助、自升级与逐题澄清。
disable-model-invocation: true
---

# Mars Development Flow

仅接受显式 `$mdf <intent>` 调用。裸 `$mdf` 与 `$mdf help` 显示帮助目录。

## 选择树

```text
┌──────────────────────────────────┐
│ 1 Accept call                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 裸调用、未知调用 ────→ [帮助并结束]
                 │
                 ▼ 有效显式调用
┌──────────────────────────────────┐
│ 2 Check CLI                      │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Dispatch                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 边界不明 ─────────────────────────────→ 3 Dispatch
                 ├──── 材料缺失 ─────────────────────────────→ [停止并报告]
                 │
                 ├──── bootstrap ────────────────────────────→ references/bootstrap.md
                 ├──── init migrate / migrate ───────────────→ references/migrate.md
                 ├──── init ─────────────────────────────────→ references/init.md
                 ├──── intake ───────────────────────────────→ references/intake.md
                 ├──── tree [--depth N] ─────────────────────→ references/tree.md
                 ├──── prp tree ─────────────────────────────→ references/tree.md
                 ├──── next? / next？ ───────────────────────→ references/tree.md
                 ├──── next [--depth N] ─────────────────────→ references/next.md
                 ├──── deliver [<target>] [--auto-pilot] ────→ references/deliver.md
                 ├──── start ────────────────────────────────→ references/start.md
                 ├──── design ───────────────────────────────→ references/design.md
                 ├──── write-tests ──────────────────────────→ references/write-tests.md
                 ├──── implement ────────────────────────────→ references/implement.md
                 ├──── converge ─────────────────────────────→ references/converge.md
                 ├──── code-review ──────────────────────────→ references/code-review.md
                 ├──── fact update ──────────────────────────→ references/fact-update.md
                 ├──── prp split ────────────────────────────→ references/prp-split.md
                 ├──── finish ───────────────────────────────→ references/finish.md
                 ├──── fact audit ───────────────────────────→ references/fact-audit.md
                 ├──── clarify <议题> ───────────────────────→ references/clarify.md
                 ├──── bug create ───────────────────────────→ references/bug-create.md
                 ├──── prp create ───────────────────────────→ references/prp-create.md
                 ├──── prp review ───────────────────────────→ references/prp-review.md
                 ├──── archive ──────────────────────────────→ references/archive.md
                 ├──── codewiki generate ────────────────────→ references/codewiki-generate.md
                 ├──── codewiki update ──────────────────────→ references/codewiki-update.md
                 ├──── jot / jot promote ────────────────────→ references/jot.md
                 ├──── help / help <intent> ─────────────────→ references/help.md
                 └──── upgrade ──────────────────────────────→ references/upgrade.md
```

## 工作流（唯一执行契约）

入口与各 intent 只按编号工作流执行；图示仅用于路由。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 调用 | 约束 | 只接受显式 intent；问号 next 走 tree | 有效显式调用 | 2 | 帮助并结束 |
| 2 | 工具 | 脚本 | 定位 MDF_ROOT，运行 `info` 并核对版本 | CLI 结果、三个版本为 2 | 3 | 停止 |
| 3 | 分流 | 约束 | 核对目标根并执行命中流程 | 目标根或豁免、流程结果 | 返回调用方 | 澄清后回到 3；其他停止 |

## 术语与数据结构

### 调用与工具

只接受选择树所列的显式调用。裸调用或未知调用按 help 执行。`next [--depth N]`
与 `tree [--depth N]` 的深度可省略；`$mdf tree`、`$mdf prp tree`、
`$mdf next?` 与 `$mdf next？` 执行 `references/tree.md`，不得当未知调用送
help。`$mdf next` 无问号时执行 `references/next.md`。
`$mdf deliver [<target>] [--auto-pilot]` 仍是 deliver，不是独立 intent。
`--auto-pilot` 可在 target 前或后；target 由 deliver 解析。
start、design、deliver、code-review 可带 `--qa-strategy`、`--dev-strategy`、
`--review-strategy`、`--models`；由对应 intent 解析并写入 roster。
未知 `--` token 停止询问。
`clarify <议题>` 的议题由对应 intent 检查，`help <intent>` 的主题由 help 检查。
除显式 next 按 `references/next.md` 续办，或 deliver 按 `references/deliver.md` 持续交付外，
不得因缺文档、代码/测试状态或对话上下文隐式选择 intent。
显式 init 可按其契约内部转入 bootstrap 或 migrate；`$mdf init migrate` 与
`$mdf migrate` 执行同一流程。next 可委托识别出的在途流程，无在途时委托
tree；deliver 可内部委托从 start 起的剩余交付阶段直到 finish；其他入口仍按
显式调用路由。

**帮助**：裸调用、未知调用读取并执行 `references/help.md`。`$mdf help` 为显式调用，
经 CLI 检查后同样执行该流程。不读取其他 intent、不检查仓库、不写入。
**MDF_ROOT**：本文件所在目录的绝对路径。确认 `scripts/mdf.py` 后运行
`python3 "$MDF_ROOT/scripts/mdf.py" info`；协议、工具与 schema 版本均须为数字 `2`。
工具缺失或检查失败时停止，不得模拟 CLI。

完整读取选择树指定的 intent，只按其声明条件读取公共引用；缺失材料时停止并报告。
将调研、已确认决策与`当前事实文档`分开，不把候选方案当作已实现行为，不替代任务管理；
按 intent 用 Markdown 与 `manifest` 留下可验证的演进记录。
除 help、clarify、upgrade 外，公开 intent 均读取 `references/common.md`。
help 与 clarify 不核 Git 根；upgrade 见 `references/upgrade.md`。
`codewiki-runtime.md` 与 `codewiki-recovery.md` 不读 `common.md`。
步骤 3 命中后核对目标根；边界不明澄清后回到 3，材料缺失则停止并报告。

`$mdf bug <action>`、`$mdf prp <action>`、`$mdf codewiki <action>`、`$mdf jot promote`、
`$mdf init migrate` 与 `$mdf help <intent>` 均由选择树路由；
这些内部材料不是独立 Skill。 CLI 形式为 `python3 "$MDF_ROOT/scripts/mdf.py" <command>`；
command 与用户 intent 不要求一一对应。CLI 统一解析目标 Git 根，不假设当前目录就是目标仓库。
