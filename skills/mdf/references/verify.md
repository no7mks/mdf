# verify

对当前交付分支运行 module 级验证。开发中只用 on-site；closeout、非 feature
审查前 Verify、以及非 feature 证据过期补验才跑 full（feature 过期补 on-site）。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve modules                │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ module 已确定
┌──────────────────────────────────┐
│ 2 Select                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 范围与命令已定
┌──────────────────────────────────┐
│ 3 Run                            │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败 ────→ [停止并报告]
                 │
                 ▼ 命令通过
┌──────────────────────────────────┐
│ 4 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 需重跑 ───────→ 3
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ advance 或已记录 / on-site 结束
                 [结束]
```

## 工作流（唯一执行契约）

入口：`$mdf verify run|check|advance --level on-site|full`；可选
`--module` / `--paths` / `--test`。`check`/`advance` 只用于 full。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve modules | 约束 | 读 modules；定 on-site 范围；full 要干净树 | module 列表 | 2 | 停止并报告 |
| 2 | Select | 约束 | on-site 选题；full 按分支选 smoke/release | 命令列表 | 3 | 停止并报告 |
| 3 | Run | 脚本 | `mdf.py verify run --level …`；跑 lint/build/quick + 套件 | 运行结果 | 4 | 停止并报告 |
| 4 | Record | 脚本 | full 落盘；`check`/`advance`；可回 3 | 证据或摘要 | 结束 | 需重跑→3；否则停止并报告 |

### 1 Resolve modules

- 读 `.mdf/modules.yaml`（由 `mdf.py verify` 内部完成）。
- on-site：`--paths` 命中 sourceset（非 ignore）并与 `--module` 合并。
- full：全部 module；执行前 worktree 必须干净。
- bugfix 的 full `run`：须已有 `changes/unreleased/<slug>/suites.json` 关联 ≥1
  已文档化 named suite（由 Verify 阶段写入；缺失则 `missing_delivery_suite`）。

验收：
- on-site：涉及 module 非空且均已声明。
- full：全部已声明 module；worktree 干净；bugfix 另有有效 `suites.json`。

异常与交接：未知 module、full 时 worktree 脏、或 bugfix 缺 suites 则停止。

### 2 Select

**on-site**

1. 收集涉及 module 的 named suite 列表。
2. 打开 `docs/system/testing/<suite>.md`，摘要目的与 testcase 构成。
3. 组装改动摘要。
4. Jev（或主 Agent）决定跑哪些 test/testcase；经 `--test` 传入。
5. ❌ 默认不整份跑 named suite。

验收（on-site）：命令列表不超出涉及 module。

**full**

- feature / bugfix → smoke 并集；release / hotfix → release 并集。
- 实际执行：全部 module 的 lint + build + quick + 上述套件并集。

验收（full）：命令为全 module 同名入口并集，按分支套件选择。

异常与交接：选题失败则停止。

### 3 Run

- CLI：`mdf.py verify run --level on-site|full ...`
- `check`：跳过本步，直接进 Record 校验已有证据。
- `advance`：跳过本步，直接进 Record 快进 commit。
- 失败则停止并报告。

验收：所选命令通过（`run`）；或进入 Record 处理 `check`/`advance`。

异常与交接：`verify_command_failed` 时停止。

### 4 Record

- full `run`：无论成败均写入 `changes/unreleased/<slug>/verify.full.json`
  （`commit`=HEAD）；`all_passed:false` 时 CLI 仍失败，且后续 `check` 拒收。
- `check`：证据有效、`all_passed:true`，且相对 HEAD 仅允许证据/报告增量。
- HEAD 有业务 diff：先 Jev 判是否重跑；否 → `advance`；是 → 回步骤 3 `run`。
- on-site 不持久化门禁；结果在 stdout。

验收：full 证据可 `check`；on-site 结果在 stdout；`advance` 后 commit 对齐 HEAD。

异常与交接：证据缺失、过期或 `all_passed:false` 则停止。
