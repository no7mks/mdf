# catch-up

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ───────────→ [停止并报告]
                 ├──── 无事实后增量改动 ────→ 5 Tick
                 │
                 ▼ 存在 <catch_up_base>..HEAD 改动
┌──────────────────────────────────┐
│ 2 Lint and review                │
└────────────────┬─────────────────┘
                 │
                 ├──── 未通过且无授权/不可修 ────→ [保留现场并停止]
                 │
                 ▼ 增量 lint 与单人增量审查通过
┌──────────────────────────────────┐
│ 3 Verify                         │
└────────────────┬─────────────────┘
                 │
                 ├──── smart 未通过或误触发全量 ────→ [保留现场并停止]
                 │
                 ▼ 改动路径 smart 通过
┌──────────────────────────────────┐
│ 4 Fact                           │
└────────────────┬─────────────────┘
                 │
                 ├──── paths 事实补检未通过 ────→ [保留现场并停止]
                 │
                 ▼ 无事实影响或 paths 补检通过
┌──────────────────────────────────┐
│ 5 Tick                           │
└────────────────┬─────────────────┘
                 │
                 ├──── 记录或提交失败 ────→ [保留现场并报告]
                 └──── 成功 ──────────────→ [返回调用方]
```

## 工作流（唯一执行契约）

读取 `references/common.md`、`references/delivery-contract.md` 与 `references/repository-contract.md`。
本 intent 在基线 `lint`、`code-review`、`verify`、`fact` 已通过后，仅对远端合入或收尾返工产生的增量改动文件执行补检。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check | 约束 | 核对基线四项已勾，解析 `<catch_up_base>..HEAD` 改动文件 | `objectives.md`、增量文件集 | 有改动 2；无改动 5 | 停止并报告 |
| 2 | Lint and review | Subagent | 仅对触及 module 跑 lint，并派 1 名 reviewer 审 `<catch_up_base>..HEAD` | lint 日志、增量审查追加段 | 3 | 保留现场并停止 |
| 3 | Verify | 脚本 | 仅对改动文件执行 `verify --scope smart --paths ...`，保留原报告 | smart JUnit 与增量日志 | 4 | 保留现场并停止 |
| 4 | Fact | 约束 | 仅当改动触及实现或事实页时，按 `--scope paths` 补检事实页 | paths 审阅证据 | 5 | 保留现场并停止 |
| 5 | Tick | 约束 | 更新 `catch-up` 基线至当前 `HEAD`，勾选 `catch-up` 并提交 | 已勾 `objectives.md` 与提交 | 返回调用方 | 保留现场并报告 |

## 强硬禁令（严禁全量重跑）

本阶段存在唯一目的：避免远端集成、冲突消解、PR 返工或收尾微调把已通过的基线全量门禁退勾重来。执行者必须无条件遵守以下禁令：

- ❌ **严禁退勾已通过的基线步骤**：任何情况下不得退勾已通过的 `lint`、`code-review`、`verify`；也不得将 `fact audit` / `fact update` / `fact audit/update` 改回 `[ ]`。
- ❌ **严禁触发全量验证**：严禁调用 `$mdf verify --scope branch`；严禁重跑顶层整仓 `smoke` 或 `release`；严禁清空、重置或覆盖已通过的 `verification-report.json`。
- ❌ **严禁触发全分支或全员代码审查**：严禁从 `start_commit` 或上一发布版本重审整条分支；严禁按 `roster.reviewers` 全员重派，固定只派 1 名 reviewer 审 `<catch_up_base>..HEAD`。
- ❌ **严禁触发全量事实审阅**：严禁重跑整分支 `fact audit` 或 `--scope full`；未触及业务实现与事实页时直接跳过步骤 4。
- ❌ **再次触发更新只回 `catch-up`**：`catch-up` 已勾 `[x]` 后，若 `pr` 或 `close-out` 再次引入远端合入或返工，只退勾 `catch-up`（PR mode 另退勾 `pr`），绝不回退更早步骤。

## 增量基线与范围判定

- **前置要求**：`objectives.md` 中 `catch-up` 之前的全部步骤（含 `lint`、`code-review`、`verify`、`fact`）必须已为 `[x]`；若有未勾前置，立即停止并交回对应前置，不代跑首轮基线。
- **`<catch_up_base>` 解析顺序**：
  1. 若 `objectives.md` 已记录 `catch-up 基线：<commit>`（或 `PR 返工：<left>..<right>` 的左端点 `<left>`），取最近一次已通过 `catch-up`（或进入返工前）的 `<commit>`。
  2. 否则取本分支首次完成 `fact audit` / `fact update` / `fact audit/update` 勾选提交时的 `HEAD`。
- **增量文件集**：运行 `git diff --name-only <catch_up_base>..HEAD`；剔除纯 `objectives.md` 勾选、`code-review.md`、`fact-audit.md` 与 `CHANGE.md` 后记为 `CHANGED_PATHS`。
  - 同时剔除本次材料目录中的 `catch-up-verification-report.json`，避免上一轮补检报告被当成待验实现。
- **零增量直通**：首次从 `fact` 顺序进入 `catch-up` 且 `CHANGED_PATHS` 为空时，不跑步骤 2–4；直接在步骤 5 勾选 `- [x] catch-up` 并记录 `catch-up 基线：<HEAD>`。

## 步骤细则

### 2 Lint and review（仅改动范围）

- **增量 Lint**：仅当 `CHANGED_PATHS` 含代码、测试或验证配置时，执行步骤 3 的 smart 命令并核对 lint 结果。
  - 必须带独立 `--report-file`；若 review 未再改代码、测试或验证配置，步骤 3 复用本次结果，不重复执行。
- **单人增量审查**：在 `code-review.md` 追加增量轮次，仅派 **1 名**独立 reviewer Subagent，显式传入 `diff_range: <catch_up_base>..HEAD` 与 `CHANGED_PATHS`。
- **审查边界**：reviewer 只审 `<catch_up_base>..HEAD` 的改动文件及上轮未决项，不得扩审未改动文件；通过后追加本轮结论，不覆盖首轮审查记录。

### 3 Verify（仅改动文件 smart）

- 先按 `CHANGED_PATHS` 确定触及 module，读取相关 `docs/system/testing/<suite>.md` 并选择 test/testcase。
  - 选题覆盖本轮改动测试、受影响行为及 PR/CI 反馈中的失败用例；quick 外的 E2E 或 named suite 用例也必须纳入。
  - 将每条选中的完整命令分别传入 `--test`；`--paths` 仅选择 module，不会自动选择或执行这些用例。
  - 仅在 quick 已完整覆盖所需回归时可省略 `--test`，并记录覆盖依据；无法确定回归命令时停止，不以 quick 通过替代。
- 设置 `CATCH_UP_REPORT` 为本次材料目录内独立的 `catch-up-verification-report.json`，不得指向基线 `verification-report.json`。

```bash
python3 "$MDF_ROOT/scripts/mdf.py" verify --repo "$REPO_ROOT" --scope smart \
  --paths <changed-path-1> --paths <changed-path-2> \
  --test "<选中的完整回归命令>" --report-file "$CATCH_UP_REPORT"
```

- 每个路径各带一次 `--paths`；只有一个路径时省略第二组，更多路径或测试命令继续重复对应参数。
- 仅当 `CHANGED_PATHS` 含代码、测试、fixtures 或验证配置时执行上述 `--scope smart --paths ...` 命令。
- 若改动全是测试文件或局部代码，只运行 smart 选中的目标测试文件/用例与触及 module 的 quick；**绝不调用 `--scope branch` 重跑整仓 smoke**。
- `--report-file` 使 smart 成败结果仅写入独立文件，adhoc 也不覆盖基线；普通 smart 未指定该参数时仍按原规则写报告。
- 核对增量报告中所选命令均已执行且通过；在 `code-review.md` 或 `objectives.md` 记录报告、JUnit 与日志路径。
- 授权范围内发现问题可原地修复；修复后仍以原 `<catch_up_base>..HEAD` 从步骤 2 重跑增量补检，绝不升级为全量 `branch`。

### 4 Fact（仅改动路径 paths）

- 仅当 `CHANGED_PATHS` 触及实现代码或 `GLOSSARY.md`、`docs/user-guide/`、`docs/system/` 事实页时，执行路径级事实补检：

```bash
python3 "$MDF_ROOT/scripts/mdf.py" fact-audit --repo "$REPO_ROOT" --scope paths \
  --implementation-path <实现路径> --document-path <事实页路径>
```

- 将实现与事实页分别传入对应参数；每条路径重复一次参数，无该类路径时省略，至少保留一条路径。
- 按 [fact audit](fact-audit.md) 对映射结果完成语义审阅、覆盖复核和 strict validation，不以 CLI clear 直接判定通过。
- 若需同步事实页，执行 `$mdf fact update <path>... --scope paths`，并在 `fact-audit.md` 追加增量补检摘要，不重跑整分支 `--against <start_commit>`。

### 5 Tick（勾选与循环锚点）

- 步骤 2–4 全部通过（或步骤 1 判定无实质增量改动）后，在 `objectives.md` 中：
  - 将 `- [ ] catch-up` 勾为 `- [x] catch-up`；
  - 记录或更新 `catch-up 基线：<当前 HEAD 完整 SHA>`。
- 提交 `objectives.md` 及增量审查/事实摘要，deliver 内部委托时完成后返回调用方（`deliver`、`pr` 或 `close-out`）。
