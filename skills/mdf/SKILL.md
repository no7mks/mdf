---
name: mdf
description: >-
  Mars Development Flow 的唯一入口。用户显式使用 $mdf <command> 管理仓库文档、
  审计、收口、归档或逐题澄清。
disable-model-invocation: true
---

# Mars Development Flow

只在用户显式调用 `$mdf <command>` 时执行。不要因仓库缺少文档、代码完成、
测试通过或对话上下文而隐式选择或运行工作流；绝不自动 commit。

可用命令：

| 命令 | 用途 |
| --- | --- |
| `init-repo` | 初始化或更新仓库的 MDF 文档系统 |
| `start` | 按 Gitflow 创建并推送交付分支 |
| `review-doc` | 新建或修订单个 active Requirement / Bug |
| `finish` | 按 Gitflow 分支完成文档收口 |
| `audit` | 执行 change audit 或 release audit |
| `archive` | 归档 closed Requirement 与 Bug |
| `grill <议题>` | 逐题压力测试计划、决策或想法 |

裸 `$mdf` 或未知命令时，只展示本表和调用示例，不读取工作流、不检查仓库、
不写入任何内容。`grill` 必须携带非空议题；其他命令所需的对象、版本或取舍
在流程中一次一题澄清。

## 运行约定

1. 解析本文件的绝对路径为 `MDF_ROOT`，确认 `scripts/mdf.py` 存在，运行：

   ```bash
   python3 "$MDF_ROOT/scripts/mdf.py" info
   ```

   要求 `protocol_version`、`tool_version` 与 `schema_version` 均为数字 `2`。
   命令失败或版本不符时停止；不要模拟脚本行为。
2. 仅完整读取 `workflows/<command>.md`，并遵循其按需读取公共引用的说明。
3. 所有脚本均以 `python3 "$MDF_ROOT/scripts/mdf.py"` 调用。解析目标 Git 根，
   不假设当前目录就是目标仓库。

内部材料不是可单独调用的 Skill：公共契约在 `references/`，模板在 `assets/`，
确定性 CLI 在 `scripts/`。每次外层流程开始时均要求 clean worktree；写入失败
时保留现场并报告 findings。
