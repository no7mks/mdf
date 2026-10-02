# bug close

二次验证已 `fixed` 的 Bug：只跑该 Bug 的复现用例，失败则像 converge 一样修到
通过，并仅审查这次修复的代码。通过后标为 `closed` 并写 `fixed_in`，不跑全局
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
| 2 | Verify | 约束 | 跑复现用例；失败则修并 smart（quick suite） | 命令、结果、smart | 3 | 可修或获批回 2；否则停 |
| 3 | Review | 约束 | 只审这次修复的代码并裁定 | 范围 diff、结论 | 4 | 有可修回 2；需决定则停 |
| 4 | Record | 脚本 | 写记录、关闭 Bug 并提交 | 记录、对象、提交 | 结束；finish 委托且改了实现则回 finish 4 | 停止 |

## 术语与数据结构

### 范围与前置条件

本节确定入口前置、待验证清单与写入边界。

- 解析 `REPO_ROOT` 并运行 `doctor`。验收：`normal_workflows_allowed: true`。
- 独立调用：`$mdf bug close <bug-id> --fixed-in <version>`；Bug ID 与版本必填。
- `--fixed-in` 只接受稳定 SemVer；release/hotfix 上须等于分支版本。
- feature/bugfix 上传入的版本是确定的交付目标，发版时核对实际包含该修复。
- 不切分支、不 start、不创建 worktree。写入落点按 `common.md`。
- 运行 `list --repo "$REPO_ROOT" --type bug --status fixed`，不逐篇翻阅 `docs/bugs/`。
- 待验证清单：
  - 有 Bug ID 时命中唯一 `fixed` 对象，规则同 `$mdf fix`。`open`、`closed`、`rejected` 停止。
  - finish 委托时使用调用方传入的待收入 ID 列表与发布版本，不自行扩大清单。
  - 已 closed 的 Bug 不重复关闭；finish 核对 fixed_in 与本版一致及记录有效性。
- 修复写入前（步骤 2、3）运行 `git branch --show-current`：为 `master` 或为空（detached HEAD）时
  不写入，停止并报告。只读复现验证不受此限。
- finish 委托模式：本次步骤 2–3 修改了实现、测试或验证配置时，记录并提交后向 finish 报告「实现已变更」；
  finish 回到其步骤 4 报告失效并交接；主链在 close-out 外补验与增量 code-review，
  再续办步骤 7，之后才可收口。
- ❌ 边界：
  - 只有复现验证与修复审查都通过，才写 `closed` 与 `fixed_in`。
  - 不跑 branch/named 验证；只在本步修改实现后运行下方 smart，不按分支 kind 选择 suite。
  - 可只读已有 `changes/unreleased/<slug>/verify.branch.json`（须 `all_passed: true`）。

### 复现验证

对清单中每个 Bug，对照其「所需回归证据」确认复现用例通过。

- 取证：
  - 当前分支为 bugfix/hotfix/release，且存在 `verify.branch.json` 且 `all_passed: true` 时，
    直接读该文件：
    - 用 `results[].report.cases` 判断该 test 是否 passed。
    - 报告目录是 `results[].log`，其中才有 `summary.json`。
    - passed 时引用该目录与 test 名，不重跑。
    - `results[].report.cases` 未命中该 test 时，改走下面的点名执行。
      报告全绿不表示该复现用例已跑过。
  - 非上述分支、无可用报告，或 cases 未命中时，按 `docs/system/testing/` 的命令模板
    点名执行。证据另给可执行命令时运行该命令。
- 只要求这些复现用例通过。
- 本步修改了实现时，另对涉及 module 跑 smart（含 quick suite），须退出 0。
  - CLI：`verify --scope smart --repo "$REPO_ROOT"`。
  - 用 `--paths` / `--module` 圈定涉及 module。
  - 成功读 stdout 的 `result`：逐项 `log` 与 quick `report`。
  - 非零读 stderr 最后一行的 `details.results[]`（`passed` / `error`）。
  - 不把进度行当结果。
  - ❌ 不调用 `$mdf verify --scope branch` 冒充本步。
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
  - 调用：`noul`（证据是否支持关闭结论）。
  - state：复现结果与审查 diff 摘要。
  - 采信后仍须写入依据；未采信走主 Agent。
  - ❌ 不让 Jev 代替步骤 4 的关闭写入。

### 记录

按 Bug 追加记录，落点按当前分支：

| 分支 | 落点 |
| --- | --- |
| `release/<semver>`、`hotfix/<semver>` | `changes/unreleased/<semver>/bug-close.md`（目录可新建） |
| `feature/*`、`bugfix/*`（带 Bug ID） | `changes/unreleased/<当前交付 slug>/bug-close.md`，slug 同 code-review 记录 |
| develop 或其他非交付分支 | 在 Bug 正文追加验收记录 |

- 字段：ID、复现命令与退出状态（或引用的报告路径与 test 名）、结果、审查路径范围、HEAD、结论。
- 记录须使 finish 能判断「该 ID 在当前 HEAD 上复现用例已通过且审查完成」。
- 有效性：记录 HEAD 到当前 HEAD 只改记录文件自身、`docs/` 或 `changes/` 材料（无代码变化）时仍有效；
  其他改动或复现命令变化则过期，须重跑步骤 2–3。
- 按 `common.md` 提交记录与本次修复；不夹带无关改动。
- 复现与审查通过后调用 Core CLI：
  `bug close <bug-id> --fixed-in <version> --repo "$REPO_ROOT"`。
  - Core 仅做确定性字段校验与写入，不执行复现或代码审查。
  - 写入 `status: closed`、`fixed_in: <version>`；保留 found_in，发版时再归一化。
  - 任一验证失败不得调用关闭 CLI。
  - finish 委托且修改了实现时，先交接补验；本轮不关闭，续办通过后再关闭。

验收：清单内每个 Bug 复现用例通过、修复代码已审、Bug 已 closed、fixed_in 正确，记录与对象已提交。
