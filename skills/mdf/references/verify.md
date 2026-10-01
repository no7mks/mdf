# verify

对当前交付分支运行 module 级验证。

- **on-site**：开发与 converge 使用（lint+build+quick + 改动测试/选题）。
- **full**：独立主链 intent（在 code-review 之后）；失败则**现场修到绿**。
  - 默认 suite：bugfix/hotfix → smoke；feature/release → release。
  - 不做相对 converge 的过期 gatekeeping。

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
                 ├──── full 失败且可修 ────→ 3 Run（修后重跑）
                 ├──── 需测试修改批准 ─────→ [确认后回 3]
                 ├──── 阻塞或不可修 ───────→ [停止并报告]
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
主链委托 full 时：失败须现场修到绿后再结束本 intent。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve modules | 约束 | 读 modules；定 on-site 范围；full 要干净树 | module 列表 | 2 | 停止并报告 |
| 2 | Select | 约束 | on-site 选题；full 按分支选 smoke/release | 命令列表 | 3 | 停止并报告 |
| 3 | Run | 脚本 | `mdf.py verify run`；失败则修到绿 | 运行结果 | 4 | 可修回 3；阻塞停 |
| 4 | Record | 脚本 | full 落盘；`check`/`advance`；可回 3 | 证据或摘要 | 结束 | 需重跑→3；否则停止并报告 |

### 1 Resolve modules

- 读 `.mdf/modules.yaml`。
- on-site：`--paths` 命中 sourceset（非 ignore）并与 `--module` 合并。
- full：全部 module；执行前 worktree 必须干净。
- bugfix 的 full `run`：须已有 `suites.json` 关联 ≥1 已文档化 named suite。
  缺失则 `missing_delivery_suite`。

### 2 Select

**on-site**

1. 收集涉及 module 的 named suite 列表与本分支相对 start_commit 的测试改动。
2. 打开相关 `docs/system/testing/<suite>.md`。
3. Jev（或主 Agent）决定跑哪些 test/testcase；经 `--test` 传入。
4. 默认不整份跑 named suite。

**full**

- bugfix / hotfix → smoke 并集；feature / release → release 并集。
- 实际执行：全部 module 的 lint + build + quick + 上述套件并集。

### 3 Run

- CLI：`mdf.py verify run --level on-site|full ...`
- 遵守「测试失败工作流」：框架报告 → 单用例复测 → 修一个复测一个 → 再继续。
- **full 失败**：在本 intent 现场修实现（改测试须批准），提交后保持干净树再跑，
  直到绿或死硬阻塞；不回退假阶段、不发明对 converge 的过期检查。
- `check` / `advance`：跳过本步进 Record。

### 4 Record

- full `run`：无论成败均写入 `changes/unreleased/<slug>/verify.full.json`
  （`commit`=HEAD）；`all_passed:false` 时 CLI 仍失败。
- 主链完成条件：`check` 显示有效且 `all_passed:true`。
- on-site 不持久化门禁；结果在 stdout。
- 可向 `changes/unreleased/<slug>/verify.md` 追加本次 full 摘要（suite、HEAD、报告路径）。

