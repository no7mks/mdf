---
name: mdf
description: >-
  Mars Development Flow 的唯一入口。用户显式使用 $mdf、$mdf doc、$mdf codewiki 或
  $mdf jot promote 管理仓库文档、CodeWiki、随手记录、审计、收口、归档或逐题澄清。
---

# Mars Development Flow

MDF 是面向 Git 仓库的版本化文档与交付流程。它管理`当前事实文档`、ADR、调研、
Proposal、Bug 和 Change，并以 `manifest` 约束`validation`与发布状态。它不替代
任务管理。它将调研、已确认决策与`当前事实文档`分开，避免将候选方案误作已实现行为。
从初始化到归档，MDF 以仓库内的 Markdown 和 `manifest` 留下可验证的演进记录。

只在用户显式调用 `$mdf <intent>`、`$mdf doc <action>`、
`$mdf codewiki <action>` 或 `$mdf jot promote` 时执行。不要因仓库缺少文档、
代码完成、测试通过或对话上下文而隐式选择或运行 intent；绝不自动 commit。

可用意图：

| 意图 | 用途 |
| --- | --- |
| `init` | 初始化或更新仓库的 MDF 文档系统 |
| `codewiki generate` | 用 CodeWiki MCP 新建仓库结构 Wiki |
| `codewiki update` | 增量更新符合 MDF 契约的结构 Wiki |
| `start` | 按 Gitflow 创建并推送交付分支 |
| `jot` | 追加一条未分诊的随手记录 |
| `jot promote` | 将一条 Jot 提升为 ready Proposal 或 Bug 并移除原条目 |
| `doc derive` | 从需求来源确认 MVP 并拆分 Proposal 候选 |
| `doc create` | 新建单个 active Proposal 或 Bug |
| `doc review` | 修订单个 active Proposal 或 Bug |
| `doc archive` | 归档 closed Proposal 或 Bug |
| `finish` | 按 Gitflow 分支完成文档收口 |
| `audit` | 审阅当前文档与实现的覆盖、证据和语义是否相符 |
| `grill <议题>` | 逐题压力测试计划、决策或想法 |

裸 `$mdf`、裸 `$mdf doc`、裸 `$mdf codewiki` 或未知意图时，只展示本表和调用示例，
不读取 intent、不检查仓库、不写入任何内容。`grill` 必须携带非空议题；`jot` 只接受裸调用或
`promote` 子动作；其他意图所需的对象、版本或取舍在流程中一次一题澄清。

## 运行约定

1. 解析本文件的绝对路径为 `MDF_ROOT`，确认 `scripts/mdf.py` 存在，运行：

   ```bash
   python3 "$MDF_ROOT/scripts/mdf.py" info
   ```

   要求 `protocol_version`、`tool_version` 与 `schema_version` 均为数字 `2`。
   命令失败或版本不符时停止；不要模拟脚本行为。
2. `doc derive`、`doc create`、`doc review`、`doc archive` 分别读取
   `intents/doc-derive.md`、`intents/doc-create.md`、`intents/doc-review.md` 与
   `intents/doc-archive.md`。`codewiki generate` 与 `codewiki update` 分别读取
   `intents/codewiki-generate.md` 与 `intents/codewiki-update.md`。`jot` 与
   `jot promote` 都读取 `intents/jot.md`；其他意图仅完整读取
   `intents/<intent>.md`，并遵循其按需读取公共引用的说明。
3. `$mdf <intent>`、`$mdf doc <action>`、`$mdf codewiki <action>` 与
   `$mdf jot promote` 是用户触发的 intent；
   `python3 "$MDF_ROOT/scripts/mdf.py" <command>` 是 intent 内部调用的
   确定性 CLI command。两者不要求一一对应：`init` 可调用
   `doctor` 与 `init`，`finish` 可调用 `finish-gitflow`。所有 CLI
   动作均由统一入口调用，解析目标 Git 根；不假设当前目录就是目标仓库。

## 内部材料

| 材料 | 位置 | 用途 |
| --- | --- | --- |
| 意图 | `intents/` | 定义各用户意图的语义步骤 |
| 公共契约 | `references/` | 由 intent 按需读取 |
| 模板 | `assets/` | 供 intent 写入仓库产出物 |
| 确定性 CLI | `scripts/` | 供 intent 执行确定性操作 |

上述材料均不是可单独调用的 Skill。

## 执行约束

- 仅在每次外层 intent 入口检查目标仓库为 clean worktree。
- 同一次 intent 写入后，可按用户反馈继续修改，不得再次以 dirty 拒绝。
- 写入失败时保留现场，并报告 findings。
