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
                 ├──── 可修复实现问题 ────→ 2 Verify
                 ├──── 需测试修改批准 ────→ [主会话确认后 resume 回 2]
                 ├──── 三轮无进展 ────────→ [停止并报告]
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
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止并报告]
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
| 2 | Verify | 约束 | 跑复现用例；失败则修实现并重验 | 命令、退出状态、结果 | 3 | 可修或待批准回 2；三轮无进展则停 |
| 3 | Review | 约束 | 只审这次修复的代码并裁定 | 范围 diff、结论 | 4 | 有可修回 2；需决定则停 |
| 4 | Record | 脚本 | 写下二次验证记录并提交 | 记录、提交 | 结束 | 停止并报告 |

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
- ❌ 边界：
  - 不把对象标为 `closed`，不填 `fixed_in`。
  - 不跑 `project-verify` 或 `delivery verify`，不按分支 kind 选择 suite，不因此跑 release suite。

### 复现验证

对清单中每个 Bug，对照其「所需回归证据」确认复现用例通过。

- 取证：
  - `project-verify check` 有效，且其报告（`summary.json`）中该 test 结果为 passed 时，
    直接引用报告路径与 test 名，不重跑。
  - 否则按 `docs/system/testing/` 的命令模板点名执行对应 test case 或 test；
    证据另给可执行命令时运行该命令。
- 只要求这些复现用例通过；本步修改了实现时另跑 manifest 的 lint、build、quick。
- 缺可执行复现命令时停止并报告，提示先 `$mdf fix` 补红灯，不在本步新造用例。
- 失败且可修实现时原地修复并重验。
  - 可修复指同一失败未满三轮且下一步明确；否则视为无法完成。
  - 修改已有测试的断言、预期、fixture、跳过规则或验证门槛须用户明确批准；取得后原地重验。
  - 不设总轮数上限；同一失败连续三轮无进展则停止。
- 逐个处理；任一 Bug 未通过则停止，不宣称清单已验证。

### 修复代码审查

验证通过后，仅审查该 Bug 这次修复的代码。

- ❌ 不调用 `$mdf code-review`，不按上一正式发布或 start_commit 做整分支审查，不派 roster.reviewers。
- 范围取当前分支中提交说明含该 Bug ID 的提交，以及复现用例文件；`git diff` 只含这些路径。
  - 范围为空或不唯一时停止询问，不改用整分支 diff。
- 读取必要上下文，不能只看提交标题。
- 主 Agent 裁定、修复实现；修复后回到步骤 2 重跑该 Bug 的复现用例，再审新 diff。
- 降低验收或改目标须用户确认。
- 审查结论写入本步记录，须含实际依据。

### 记录

在 `changes/unreleased/<semver>/verify-fix.md` 按 Bug 追加记录。

- 字段：ID、复现命令与退出状态（或引用的报告路径与 test 名）、结果、审查路径范围、HEAD、结论。
- release/hotfix 的 `<semver>` 取当前分支版本；目录可与 `objectives.md` 同级新建。
- 记录须使 finish 能判断「该 ID 在当前 HEAD 上复现用例已通过且审查完成」。
- HEAD 前进或复现命令变化则记录过期，须重跑步骤 2–3。
- 按 `common.md` 提交记录与本次修复；不夹带无关改动，不改 Bug `status`。

验收：清单内每个 Bug 复现用例通过、修复代码已审、记录已提交或明确无新改动。
