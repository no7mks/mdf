# Verify Fix

二次验证已 `fixed` 的 Bug：只跑该 Bug 的复现用例，失败则像 converge 一样修到
通过，并仅审查这次修复的代码。不标 `closed`，不写 `fixed_in`，不跑全局
full，不替代 `$mdf code-review`。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 ├──── 空清单 ───────→ [结束]
                 │
                 ▼ 有待验证的 fixed Bug
┌──────────────────────────────────┐
│ 2 Verify                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 可修复实现问题 ────────────→ 2 Verify
                 ├──── 需测试修改批准 ────────────→ [取得用户确认后回 2]
                 ├──── 测试修改批准被拒 ──────────→ [停止并报告]
                 ├──── 缺可执行复现命令 ──────────→ [停止并报告]
                 ├──── 三轮无进展 ────────────────→ [停止并报告]
                 ├──── master/detached 需修复 ────→ [停止并报告]
                 │
                 ▼ 复现用例通过
┌──────────────────────────────────┐
│ 3 Review                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 有可修问题 ────→ 2 Verify
                 ├──── 需用户决定 ────→ [停止并报告]
                 │
                 ▼ 审查无问题
┌──────────────────────────────────┐
│ 4 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────────────────→ [结束]
                 ├──── 无落盘分支 ───────────────→ [仅会话报告后结束]
                 ├──── finish 委托且改了实现 ────→ [返回 finish 4 Recheck]
                 └──── 失败/缺失 ────────────────→ [停止并报告]
```

## 工作流（唯一执行契约）

读取 `references/common.md` 与 `references/object-contract.md`。
复现命令对照 `references/fix.md` 的红灯与回归证据规则。
CLI 使用 `python3 "$MDF_ROOT/scripts/mdf.py"`。
独立调用只推进当前 intent；finish 内部委托时完成后返回调用方。
不由 deliver 直接委托。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check | 脚本 | 核对 ready、待收入的 `fixed` Bug | doctor、list、参数 | 有清单则 2；空清单则结束 | 停止并报告 |
| 2 | Verify | 约束 | 跑复现用例；失败则修并 `quick-run` | 命令、结果、quick-run | 3 | 可修或获批回 2；否则停 |
| 3 | Review | 约束 | 只审这次修复的代码并裁定 | 范围 diff、结论 | 4 | 有可修回 2；需决定则停 |
| 4 | Record | 脚本 | 写下二次验证记录并提交 | 记录、提交或会话报告 | 结束；finish 委托且改了实现则回 finish 4 | 停止 |

## 术语与数据结构

### 范围与前置条件

本节确定入口前置、待验证清单与写入边界。

- 解析 `REPO_ROOT` 并运行 `doctor`。验收：`normal_workflows_allowed: true`。
- 可选位置参数至多一个 Bug ID；其他 `--` token 按入口未知参数停止。
- 不切分支、不 start、不创建 worktree。写入落点按 `common.md`。
- 运行 `list --repo "$REPO_ROOT" --type bug --status fixed`，不逐篇翻阅 `docs/bugs/`。
- 待验证清单：
  - 有 Bug ID 时命中唯一 `fixed` 对象，规则同 `$mdf fix`。`open`、`closed`、`rejected` 停止。
  - 无 ID 时：当前分支须为 `release/<semver>` 或 `hotfix/<semver>`；
    清单为 `found_in: unreleased` 的 `fixed` Bug，加上 child Change `fixed:` 中仍为 `fixed` 的 ID。
    空清单则结束，不报失败。
  - finish 委托时使用调用方传入的待收入 ID 列表，不再自行扩大。
- 修复写入前（步骤 2、3）运行 `git branch --show-current`：为 `master` 或为空（detached HEAD）时
  不写入，停止并报告。只读复现验证不受此限。
- finish 委托模式：本次步骤 2–3 修改了实现、测试或验证配置时，记录并提交后向 finish 报告「实现已变更」；
  finish 回到其步骤 4 补验与增量 code-review，再重跑其步骤 7，之后才可收口。
- ❌ 边界：
  - 不把对象标为 `closed`，不填 `fixed_in`。
  - 不跑 `project-verify run` 或 `delivery verify`，不按分支 kind 选择 suite，不因此跑 release suite。
  - 仅允许只读 `project-verify check` 用于引用已有报告。

### 复现验证

对清单中每个 Bug，对照其「所需回归证据」确认复现用例通过。

- 取证：
  - 当前分支为 bugfix/hotfix/release 且 `project-verify check` 退出 0 时，读 stdout 的 `result`。
    - 用 `results[].report.cases` 判断该 test 是否 passed。
    - 报告目录是 `results[].log`，其中才有 `summary.json`。
    - passed 时引用该目录与 test 名，不重跑。
    - `results[].report.cases` 未命中该 test 时，改走下面的点名执行。
      check 全绿不表示该复现用例已跑过。
  - 非上述分支、check 非零，或 cases 未命中时，按 `docs/system/testing/` 的命令模板点名执行。
    证据另给可执行命令时运行该命令。
  - ⚠️ `common.md` 非零退出规则的明确例外：check 非零退出不走失败去向，只改用上一条点名执行。
- 只要求这些复现用例通过；本步修改了实现时另运行 `quick-run --repo "$REPO_ROOT"`，须退出 0。
  - 成功读 stdout 的 `result`：`head`、逐项 `log` 与 quick `report`。
  - 非零读 stderr 最后一行的 `details.results[]`（`passed` / `error`），不把进度行当结果。
- 缺可执行复现命令时停止并报告，提示先 `$mdf fix` 补红灯，不在本步新造用例。
- 失败且可修实现时原地修复并重验。
  - 可修复指同一失败未满三轮且下一步明确；否则视为无法完成。
  - 修改已有测试的断言、预期、fixture、跳过规则或验证门槛须用户明确批准；
    取得用户确认后回到本步重验，被拒则停止并报告。
  - 不设总轮数上限；同一失败连续三轮无进展则停止。
- 逐个处理；任一 Bug 未通过则停止，不宣称清单已验证。

### 修复代码审查

验证通过后，仅审查该 Bug 这次修复的代码。

- ❌ 不调用 `$mdf code-review`，不按上一正式发布或 start_commit 做整分支审查，不派 roster.reviewers。
- 修复提交：提交说明含完整 Bug ID，且改动 `docs/` 与 `changes/` 以外路径。
  - `$mdf fix` 与 release/hotfix 上的直接修复均须含 ID。
  - 只改对象或记录的提交不计入。
  - 列出：`git log --fixed-strings --grep=<完整 Bug ID> --format=%H HEAD -- . ':(exclude)docs' ':(exclude)changes'`。
  - 端点：左为最早修复提交的父提交，右为最新修复提交；本 intent 已有未提交修复时右端点取工作区。
  - `git diff` 只含修复提交改过的非 `docs/`、非 `changes/` 路径与复现用例文件。
  - 范围为空或不唯一时停止询问，不改用整分支 diff。
- 读取必要上下文，不能只看提交标题。
- 主 Agent 裁定、修复实现；修复后回到步骤 2 重跑该 Bug 的复现用例，再审新 diff。
- 降低验收或改目标须用户确认。
- 审查结论写入本步记录，须含实际依据。
- 可选加速（见 `common.md`「Jev 可选加速」）：
  - 时机：复现已绿后、裁定前；tool 可用时。
  - 调用：`noul`（证据是否支持保持 `fixed` 结论）。
  - state：复现结果与审查 diff 摘要。
  - 采信后仍须写入依据；未采信走主 Agent。
  - ❌ 不因 Jev 改 `closed` / `fixed_in`。

### 记录

按 Bug 追加记录，落点按当前分支：

| 分支 | 落点 |
| --- | --- |
| `release/<semver>`、`hotfix/<semver>` | `changes/unreleased/<semver>/verify-fix.md`（目录可新建） |
| `feature/*`、`bugfix/*`（带 Bug ID） | `changes/unreleased/<当前交付 slug>/verify-fix.md`，slug 同 code-review 记录 |
| develop 或其他非交付分支 | 不落盘，仅在会话中报告；finish 只依赖 release/hotfix 的记录 |

- 字段：ID、复现命令与退出状态（或引用的报告路径与 test 名）、结果、审查路径范围、HEAD、结论。
- 记录须使 finish 能判断「该 ID 在当前 HEAD 上复现用例已通过且审查完成」。
- 有效性：记录 HEAD 到当前 HEAD 只改记录文件自身、`docs/` 或 `changes/` 材料（无代码变化）时仍有效；
  其他改动或复现命令变化则过期，须重跑步骤 2–3。
- 按 `common.md` 提交记录与本次修复；不夹带无关改动，不改 Bug `status`。
  - 不落盘分支上本次修复仍按 `common.md` 提交。

验收：清单内每个 Bug 复现用例通过、修复代码已审、记录已提交或明确无新改动。
