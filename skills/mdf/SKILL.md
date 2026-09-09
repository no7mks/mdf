---
name: mdf
description: >-
  管理 Git 仓库的版本化文档与交付流程：项目起步、初始化、规划、分诊、CodeWiki、随手记录、
  审计、收口、归档与逐题澄清。
disable-model-invocation: true
---

# Mars Development Flow

仅接受显式 `$mdf <intent>` 调用。裸 `$mdf` 只显示帮助。

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
                 ├──── bootstrap ────→ references/bootstrap.md
                 ├──── init ────→ references/init.md
                 ├──── intake ────→ references/intake.md
                 ├──── next [--depth N] ────→ references/next.md
                 ├──── start ────→ references/start.md
                 ├──── design ────→ references/design.md
                 ├──── write-tests ────→ references/write-tests.md
                 ├──── implement ────→ references/implement.md
                 ├──── converge ────→ references/converge.md
                 ├──── review ────→ references/review.md
                 ├──── fact update ────→ references/fact-update.md
                 ├──── prp split ────→ references/prp-split.md
                 ├──── finish ────→ references/finish.md
                 ├──── fact audit ────→ references/fact-audit.md
                 ├──── clarify <议题> ────→ references/clarify.md
                 ├──── bug create ────→ references/bug-create.md
                 ├──── prp create ────→ references/prp-create.md
                 ├──── prp review ────→ references/prp-review.md
                 ├──── archive ────→ references/archive.md
                 ├──── codewiki generate ────→ references/codewiki-generate.md
                 ├──── codewiki update ────→ references/codewiki-update.md
                 ├──── jot / jot promote ────→ references/jot.md
                 ├──── 目标边界不明 ────→ [澄清后重查]
                 ├──── 解析失败或材料缺失 ────→ [报告并停止]
```

## 工作流（唯一执行契约）

入口与各 intent 只按编号工作流执行；图示仅用于路由。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 调用 | 约束 | [识别显式调用](#s1) | 有效意图 | 2 | 帮助并结束 |
| 2 | 工具 | 脚本 | [运行 info](#s2) | 三个版本为 2 | 3 | 停止 |
| 3 | 分流 | 约束 | [解析目标并读取流程](#s3) | 目标根、流程结果 | 返回调用方 | 边界不明澄清；其他停止 |

## 术语与数据结构

### 执行约束

下列明细补充表中操作、证据与异常处理；步骤顺序和跳转只由上表规定。

<a id="s1"></a>

**调用**

只接受选择树所列的显式调用；`next [--depth N]` 的深度可省略， `clarify <议题>` 的议题由对应 intent 检查。
不得因缺文档、代码/测试状态或对话上下文隐式选择 intent。
显式 init 可按其契约内部转入 bootstrap；其他入口仍按显式调用路由。

验收：完整、非空的调用。

异常与交接：仅展示意图表与调用示例， 不读取 intent、不检查仓库、不写入。

<a id="s2"></a>

**工具**

将本文件所在目录的绝对路径设为 `MDF_ROOT`，确认 `scripts/mdf.py`，运行 `python3 "$MDF_ROOT/scripts/mdf.py" info`
。

验收：三个版本均为数字 `2`。

异常与交接：停止，不得模拟 CLI。

<a id="s3"></a>

**分流**

除 init/bootstrap 外，执行仓库操作的 intent 在本次调用中先将用户指定目标或当前目录
用 `git -C <目标目录> rev-parse --show-toplevel` 解析为绝对 `REPO_ROOT`，再读取并执行对应流程。
核对解析出的仓库确为用户目标；边界不明先澄清，命令失败则报告并停止，不使用空值或上次调用的变量。
clarify 不要求 Git 仓库；init/bootstrap 由 initialization 公共流程处理普通目录与父仓库边界。

完整读取选择树指定的 intent，并只按其按需读取说明读取公共引用； 将调研、已确认决策与`当前事实文档`分开，
不把候选方案当作已实现行为， 不替代任务管理；按 intent 用 Markdown 与 `manifest` 留下可验证的演进记录，
写入型 intent 允许并鼓励主动本地提交，遵守 `references/common.md` 的范围与历史规则；
提交不代替确认或验收，远端和集成操作按各自流程授权。

验收：本次目标根解析结果（适用时）、已读取材料与其流程结果。

异常与交接：停止并报告缺失材料。

| 材料 | 位置 | 读取条件 |
| --- | --- | --- |
| 意图 | `references/` | 读取显式调用命中的流程及其声明委托的内部流程 |
| 公共契约 | `references/` | 按 intent 指定读取目录、对象或 CodeWiki 契约 |
| 模板 | `assets/` | intent 要求写入仓库产出物时读取对应模板 |
| 确定性 CLI | `scripts/` | intent 要求确定性操作时调用 |

`$mdf bug <action>`、`$mdf prp <action>`、`$mdf codewiki <action>` 与 `$mdf jot promote` 均由选择树路由；
这些内部材料不是独立 Skill。 CLI 形式为 `python3 "$MDF_ROOT/scripts/mdf.py" <command>`；
command 与用户 intent 不要求一一对应。CLI 统一解析目标 Git 根，不假设当前目录就是目标仓库。
