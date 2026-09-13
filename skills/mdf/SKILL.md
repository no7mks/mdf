---
name: mdf
description: >-
  管理 Git 仓库的版本化文档与交付流程：项目起步、初始化、规划、分诊、CodeWiki、随手记录、
  审计、收口、归档、帮助、自升级与逐题澄清。
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
                 ├──── bootstrap ───────────────→ references/bootstrap.md
                 ├──── init ────────────────────→ references/init.md
                 ├──── intake ──────────────────→ references/intake.md
                 ├──── next [--depth N] ────────→ references/next.md
                 ├──── start ───────────────────→ references/start.md
                 ├──── design ──────────────────→ references/design.md
                 ├──── write-tests ─────────────→ references/write-tests.md
                 ├──── implement ───────────────→ references/implement.md
                 ├──── converge ────────────────→ references/converge.md
                 ├──── review ──────────────────→ references/review.md
                 ├──── fact update ─────────────→ references/fact-update.md
                 ├──── prp split ───────────────→ references/prp-split.md
                 ├──── finish ──────────────────→ references/finish.md
                 ├──── fact audit ──────────────→ references/fact-audit.md
                 ├──── clarify <议题> ──────────→ references/clarify.md
                 ├──── bug create ──────────────→ references/bug-create.md
                 ├──── prp create ──────────────→ references/prp-create.md
                 ├──── prp review ──────────────→ references/prp-review.md
                 ├──── archive ─────────────────→ references/archive.md
                 ├──── codewiki generate ───────→ references/codewiki-generate.md
                 ├──── codewiki update ─────────→ references/codewiki-update.md
                 ├──── jot / jot promote ───────→ references/jot.md
                 ├──── help / help <intent> ────→ references/help.md
                 ├──── upgrade ─────────────────→ references/upgrade.md
                 ├──── 目标边界不明 ────────────→ [澄清后重查]
                 └──── 解析失败或材料缺失 ──────→ [报告并停止]
```

## 工作流（唯一执行契约）

入口与各 intent 只按编号工作流执行；图示仅用于路由。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 调用 | 约束 | 只接受显式 intent；裸调用或未知调用按 help 执行 | 有效显式调用 | 2 | 帮助并结束 |
| 2 | 工具 | 脚本 | 定位 MDF_ROOT，运行 `info` 并核对版本 | CLI 结果、三个版本为 2 | 3 | 停止 |
| 3 | 分流 | 约束 | 核对本次目标根，读取命中流程并执行 | 目标根、流程结果 | 返回调用方 | 边界不明澄清后重查；其他停止 |

## 术语与数据结构

### 调用与工具

只接受选择树所列的显式调用；`next [--depth N]` 的深度可省略，亦可写成
`$mdf next?` 或 `$mdf next？`（问号不是独立 intent，判定见 `references/next.md`）。
`clarify <议题>` 的议题由对应 intent 检查，`help <intent>` 的主题由 help 检查。
除显式 next 按 `references/next.md` 识别并续办在途流程外，
不得因缺文档、代码/测试状态或对话上下文隐式选择 intent。
显式 init 可按其契约内部转入 bootstrap；next 可委托识别出的在途流程；其他入口仍按显式调用路由。

**帮助**：裸调用、未知调用读取并执行 `references/help.md`。`$mdf help` 为显式调用，
经 CLI 检查后同样执行该流程。不读取其他 intent、不检查仓库、不写入。
**MDF_ROOT**：本文件所在目录的绝对路径。确认 `scripts/mdf.py` 后运行
`python3 "$MDF_ROOT/scripts/mdf.py" info`；协议、工具与 schema 版本均须为数字 `2`。
工具缺失或检查失败时停止，不得模拟 CLI。

完整读取选择树指定的 intent，只按其声明条件读取公共引用；缺失材料时停止并报告。
将调研、已确认决策与`当前事实文档`分开，不把候选方案当作已实现行为，不替代任务管理；
按 intent 用 Markdown 与 `manifest` 留下可验证的演进记录。
写入型 intent 读取 `references/common.md`；upgrade 不读该文件，见
`references/upgrade.md`。

`$mdf bug <action>`、`$mdf prp <action>`、`$mdf codewiki <action>`、`$mdf jot promote`
与 `$mdf help <intent>` 均由选择树路由；
这些内部材料不是独立 Skill。 CLI 形式为 `python3 "$MDF_ROOT/scripts/mdf.py" <command>`；
command 与用户 intent 不要求一一对应。CLI 统一解析目标 Git 根，不假设当前目录就是目标仓库。
