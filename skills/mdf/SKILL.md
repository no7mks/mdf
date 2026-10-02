---
name: mdf
description: >-
  管理 Git 仓库的版本化文档与交付流程：项目起步、初始化、已有项目迁移、规划、分诊、
  CodeWiki、随手记录、审计、收口、归档、帮助、自升级与压力测试。
disable-model-invocation: true
---

# Mars Development Flow

仅接受显式 `$mdf <intent>` 调用。裸 `$mdf` 与 `$mdf help` 显示帮助目录。

不在回复开头打印工作区横幅。单行格式固定：

`` 📍**<main-repo-name>@<branch>** 📂 `<worktree full path>` ``

- `<main-repo-name>`：主仓库目录名（`git-common-dir` 的父目录名）。
- `<worktree full path>`：本会话当前绑定的目标 worktree 绝对路径；未绑定则
  `git rev-parse --show-toplevel`。
- `<branch>`：对该绑定路径执行 `git -C <工作根> branch --show-current`；
  detached 时 `HEAD`；非 Git 时 `-`。
- 进入或重新绑定目标后，横幅必须用新路径与新分支，不得沿用上一处绑定。
- `<branch>` 等于该路径最后两级（用 `/` 连接）时，不打印 `📂` 与目录。
- 相对上一处横幅，worktree 或 branch 变化时立刻连续打印恰好三行（硬换行）：
  1. 旧横幅全文
  2. 仅 `⬇️`（前后无空格、无其它字符）
  3. 新横幅全文
  - 实际输出为裸三行硬换行，不包代码围栏；样例见 `common.md`「工作区横幅」。
  - ❌ 禁止把 `⬇️` 与旧/新横幅写在同一行。
  - ❌ 禁止在这三行之间插入空行或其它文字。
  - 含仅改绝对路径绑定、未调用 `move_agent_to_root` 的情况。
- 没有上一处横幅时不打印切换三行。
- 本轮输出结束、等待用户回复时，最后一行必须是当前横幅。
  - 切换后的横幅已是最后一行时，不再重复。
- ❌ 不得在回复开头打印。
- 对任何 agent、任何 intent（含 help、clarify、upgrade）都生效。

## 选择树

```text
┌──────────────────────────────────┐
│ 1 Accept call                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 裸调用、未知 intent ────────────→ [帮助并结束]
                 ├──── 已知 intent 带未知 -- token ────→ [停止询问]
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
                 ├──── 边界不明 ──────────────────────────────────────→ 3 Dispatch
                 ├──── 材料缺失 ──────────────────────────────────────→ [停止并报告]
                 │
                 ├──── bootstrap ─────────────────────────────────────→ references/bootstrap.md
                 ├──── init migrate / migrate ────────────────────────→ references/migrate.md
                 ├──── init ──────────────────────────────────────────→ references/init.md
                 ├──── intake ────────────────────────────────────────→ references/intake.md
                 ├──── tree [--depth N] ──────────────────────────────→ references/tree.md
                 ├──── prp tree ──────────────────────────────────────→ references/tree.md
                 ├──── next? / next？ ────────────────────────────────→ references/tree.md
                 ├──── next [--depth N] ──────────────────────────────→ references/next.md
                 ├──── deliver [<target>] [--auto-pilot] [--yolo] ────→ references/deliver.md
                 ├──── start ─────────────────────────────────────────→ references/start.md
                 ├──── design ────────────────────────────────────────→ references/design.md
                 ├──── write-tests ───────────────────────────────────→ references/write-tests.md
                 ├──── implement ─────────────────────────────────────→ references/implement.md
                 ├──── converge ──────────────────────────────────────→ references/converge.md
                 ├──── fix <bug-id> [--yolo] ─────────────────────────→ references/fix.md
                 ├──── verify-fix [<bug-id>] ─────────────────────────→ references/verify-fix.md
                 ├──── code-review ───────────────────────────────────→ references/code-review.md
                 ├──── verify ────────────────────────────────────────→ references/verify.md
                 ├──── fact update ───────────────────────────────────→ references/fact-update.md
                 ├──── fact audit ────────────────────────────────────→ references/fact-audit.md
                 ├──── prp split ─────────────────────────────────────→ references/prp-split.md
                 ├──── close-out / finish ────────────────────────────→ references/close-out.md
                 ├──── squash [--dry-run] ────────────────────────────→ references/squash.md
                 ├──── prettify ──────────────────────────────────────→ references/prettify.md
                 ├──── clarify <议题> ────────────────────────────────→ references/clarify.md
                 ├──── bug create ────────────────────────────────────→ references/bug-create.md
                 ├──── prp create ────────────────────────────────────→ references/prp-create.md
                 ├──── prp review ────────────────────────────────────→ references/prp-review.md
                 ├──── archive ───────────────────────────────────────→ references/archive.md
                 ├──── codewiki generate ─────────────────────────────→ references/codewiki-generate.md
                 ├──── codewiki update ───────────────────────────────→ references/codewiki-update.md
                 ├──── jot / jot promote ─────────────────────────────→ references/jot.md
                 ├──── help / help <intent> ──────────────────────────→ references/help.md
                 ├──── upgrade ───────────────────────────────────────→ references/upgrade.md
                 ├──── to <target> ───────────────────────────────────→ references/to.md
                 ├──── sync ──────────────────────────────────────────→ references/sync.md
                 └──── integrate ─────────────────────────────────────→ references/integrate.md
```

## 工作流（唯一执行契约）

入口与各 intent 只按编号工作流执行；图示仅用于路由。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Accept call | 约束 | 只接受选择树所列显式 intent | 有效显式调用 | 2 | 裸或未知则帮助；带未知 -- 则停止询问 |
| 2 | Check CLI | 脚本 | 定位 MDF_ROOT，运行 `info` 并核对版本 | CLI 结果、三个版本为 3 | 3 | 停止 |
| 3 | Dispatch | 约束 | 先核目标根再按选择树执行 | 目标根或豁免、流程结果 | 按选择树返回 | 不明回 3；缺材料停止并报告 |

## 术语与数据结构

### 调用与工具

只接受选择树所列的显式调用。先判 intent：裸调用或未知 intent 按 help 执行；
已知 intent 带未知 `--` token 才停止询问。

- `next [--depth N]` 与 `tree [--depth N]` 的深度可省略。
  - `$mdf tree`、`$mdf prp tree`、`$mdf next?` 与 `$mdf next？` 执行 `references/tree.md`，
    不得当未知调用送 help。
  - `$mdf next` 无问号时执行 `references/next.md`。
- `$mdf deliver [<target>] [--auto-pilot] [--yolo]` 仍是 deliver，不是独立 intent。
  - `--auto-pilot` 与 `--yolo` 可在 target 前或后；target 由 deliver 解析。
- `$mdf fix <bug-id> [--yolo]` 仍是 fix；`--yolo` 可在 bug-id 前或后。
  - `--yolo` 仅自动确认内部 clarify，不跳过红灯，不跳过 Gitflow 收口，也不代替测试门槛批准。
- `$mdf verify-fix [<bug-id>]` 仍是 verify-fix；无 ID 时只在 release/hotfix 上处理待收入的 `fixed` Bug。
- `$mdf verify` 可带 `--scope smart|branch|named`（必选）、`--suites`（named）、
  `--module`、`--paths`、`--test`；以及子命令 `run`（由 verify 解析）。
- start、deliver 可带 `--roster`（尚未 start 时展开；已 start 则停止）。
- start、design、deliver、code-review 可带下列参数，由对应 intent 解析并写入 roster：
  - `--qa-strategy`、`--dev-strategy`、`--review-strategy`；
  - `--write-tests-model`、`--implement-model`、`--code-review-model`。
  - `--*-model` 值为口语描述，可点名一个或多个模型。
- fact update、fact audit、prettify 可带 `--scope branch|full|paths`（省略为 branch）。
  - 也可列出 `<path>...`，即 `--scope paths`；路径与冲突处理由对应 intent 解析。
- upgrade 可带 `--source`。
- ❌ 未知 `--` token 停止询问。
- `clarify <议题>` 的议题由对应 intent 检查，`help <intent>` 的主题由 help 检查。
- `$mdf to <target>` 仍是 to；空目标由该 intent 列出已知目标后停止。

intent 只由显式调用选择：

- ❌ 不得因缺文档、代码/测试状态或对话上下文隐式选择 intent。
  - 例外：显式 next 按 `references/next.md` 续办，或 deliver 按 `references/deliver.md` 持续交付。
- 显式 init 可按其契约内部转入 bootstrap 或 migrate；`$mdf init migrate` 与 `$mdf migrate` 执行同一流程。
- next 可委托识别出的在途流程，无在途时委托 tree。
- deliver 可内部委托从 start 起的剩余交付阶段直到 close-out。
- `$mdf close-out` 与 `$mdf finish` 同义，均执行 `references/close-out.md`。
- `$mdf squash [--dry-run]` 仍是 squash；`--dry-run` 只产出建议、不改写历史。
- 其他入口仍按显式调用路由。

帮助与 CLI：

- **帮助**：裸调用、未知调用读取并执行 `references/help.md`。
  - `$mdf help` 为显式调用，经 CLI 检查后同样执行该流程。
  - 不读取其他 intent、不检查仓库、不写入。
- **MDF_ROOT**：本文件所在目录的绝对路径。
  - 确认 `scripts/mdf.py` 后运行 `python3 "$MDF_ROOT/scripts/mdf.py" info`；
    协议、工具与 schema 版本均须为数字 `3`。
  - ❌ 工具缺失或检查失败时停止，不得模拟 CLI。

步骤 3 的执行顺序：

1. 先核对目标根（或该 intent 的豁免）；边界不明澄清后回到 3。
2. 再完整读取命中 intent，只按其声明条件读取公共引用；缺失材料时停止并报告。

- 按 intent 用 Markdown 与 `manifest` 留下可验证的演进记录。
- 除 help、clarify、upgrade 外，公开 intent 均读取 `references/common.md`。
  - help 与 clarify 不核 Git 根；upgrade 见 `references/upgrade.md`。
  - `codewiki-runtime.md` 与 `codewiki-recovery.md` 不读 `common.md`。

内部路由与 CLI 形式：

- 以下调用均由选择树路由：
  - `$mdf bug <action>`、`$mdf prp <action>`、`$mdf codewiki <action>`、`$mdf jot promote`；
  - `$mdf init migrate`、`$mdf help <intent>`、`$mdf to <target>` 与 `$mdf integrate`。
  - integrate 的 init、peer、send、poll、listen、status 不是独立 intent。
- 这些内部材料不是独立 Skill。
- CLI 形式为 `python3 "$MDF_ROOT/scripts/mdf.py" <command>`；command 与用户 intent 不要求一一对应。
- CLI 统一解析目标 Git 根，不假设当前目录就是目标仓库。
