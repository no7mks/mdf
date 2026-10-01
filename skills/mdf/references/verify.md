# verify

对当前交付分支运行 module 级验证。

- **on-site**：开发与 converge 使用（lint+build+quick + 改动测试/选题）。
- **full**：独立主链 intent（在 code-review 之后）；失败则**现场修到绿**。
  - 默认 suite：feature/bugfix/hotfix → smoke；release → release。
  - 进度认 objectives 勾选；报告为落盘证据，不以 commit 对齐审判。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve modules                │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ───────────────────→ [停止并报告]
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
                 ├──── on-site/full 失败且可修 ────→ 3 Run（提交后重跑）
                 ├──── 需测试修改批准 ─────────────→ [确认后回 3]
                 ├──── 阻塞或不可修 ───────────────→ [停止并报告]
                 │
                 ▼ 命令通过
┌──────────────────────────────────┐
│ 4 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ──────────────────→ [停止并报告]
                 │
                 ▼ on-site 结束；或 full 已记录并通过
                 [结束]
```

## 工作流（唯一执行契约）

入口：`$mdf verify run --level on-site|full`；可选
`--module` / `--paths` / `--test`。
主链委托 full 时：失败须现场修到绿后再结束本 intent。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve modules | 约束 | 读 modules；定范围；full 要干净树 | module 列表 | 2 | 停止并报告 |
| 2 | Select | 约束 | on-site 选题；full 选 smoke/release | 命令列表 | 3 | 停止并报告 |
| 3 | Run | 脚本 | `mdf.py verify run`；失败则修到绿 | 运行结果 | 4 | 可修/待批准回 3；阻塞停 |
| 4 | Record | 脚本 | full 落盘；勾选并提交 | 证据或摘要 | 结束 | 停止并报告 |

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

- feature / bugfix / hotfix → smoke 并集；release → release 并集。
- 实际执行：全部 module 的 lint + build + quick + 上述套件并集。

### 3 Run

- CLI：`mdf.py verify run --level on-site|full ...`
- 遵守「测试失败工作流」：框架报告 → 单用例复测 → 修一个复测一个 → 再继续。
- **失败（on-site 或 full）**：在本 intent 现场修实现（改测试须批准）。
  - 提交所改实现/测试路径后保持干净树再跑，直到绿或死硬阻塞。
  - 不回退假阶段、不发明对 converge 的过期检查。
- 修代码时**自行从架构师角度审视**修复是否合适（范围、边界、与设计一致性）。
  - ❌ 不因此强制重开 `$mdf code-review`。
  - 审视要点写入 `changes/unreleased/<slug>/verify.md`（与 full 摘要同文件）。
- 本 intent 内出现业务改动（实现/测试/验证配置）：提交或还原后重跑本步，直到绿。

### 4 Record

- full `run`：无论成败均写入 `changes/unreleased/<slug>/verify.full.json`；
  **report**，非 gate；不含 commit / head；`all_passed:false` 时 CLI 仍失败。
- 主链完成条件：本 intent 内 full 已绿（`all_passed:true`），且已自勾 objectives 的
  verify full 项并提交。
  - ❌ 不以相对下游 intent 的过期审判或 commit 对齐作为本步通行证。
- on-site 不持久化为进度；结果在 stdout。
- full 通过后向 `changes/unreleased/<slug>/verify.md` 追加摘要：
  suite、报告路径、修绿时的架构审视要点；再勾 `objectives.md` 的 verify full。
- quick 复现结论只写本文件，不写 `code-review.md`
  （审查轮次的 quick 复现仍由 code-review 自记）。
