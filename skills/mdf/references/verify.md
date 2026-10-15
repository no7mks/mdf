# verify

按 scope 运行验证；branch 要求交付分支，smart/named 不要求。

- **smart**：开发与 converge 使用（lint+build+quick + 改动测试/选题）。
- **branch**：独立主链 intent（在 code-review 之后）；失败则**现场修到绿**。
  - 默认 suite：feature/bugfix/hotfix → smoke；release → release。
  - 进度认 objectives 勾选；报告为落盘证据，不以 commit 对齐审判。
- **named**：按 `--suites` 跑指定 suite（五固定或真 named）；不写 branch 证据。
  - 真 named 命令来自 testing 文档 frontmatter；可多命令，默串行，可 `parallel`。

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
                 ├──── 运行前缺前置 ────→ [停止并报告]
                 │
                 ▼ 本轮命令已执行（含失败）
┌──────────────────────────────────┐
│ 4 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── branch 未绿且实现可修 ────→ 3 Run（提交后重跑）
                 ├──── branch 需改测试门槛 ──────→ [确认后回 3]
                 ├──── branch 未绿且阻塞 ────────→ [停止并报告]
                 ├──── 落盘/勾选失败 ────────────→ [停止并报告]
                 │
                 ▼ smart/named 结束；或 branch 已绿并勾选
                 [结束]
```

## 工作流（唯一执行契约）

adhoc 的主链执行 smart；Core 成败均保存 smart report，通过后自勾 verify smart。
开发或 code-review 内部 smart 不勾主链项；主链验证中修改业务内容则退勾 code-review 及后续项并交接。
人工 feature 的 objectives 项名为 verify smoke；执行 branch scope，沿用 feature
的 lint/build/quick/smoke 和 branch 报告要求，通过后自勾 verify smoke。
在该交付上 `$mdf verify smoke` 也按此 branch 主链解释，不走 named shortcut。


读取 `references/common.md` 与 `references/delivery-contract.md`。

入口：`$mdf verify [arg]`；arg 为 smart/branch/named 时按 scope 解析，其他值
作为 named suite 名。也可显式使用 `--scope smart|branch|named`；可选
`--module` / `--paths` / `--test`。

- 位置参数不与 `--scope` 同用；仅 `named` 可带 `--suites`。
- `verify named` 需通过 `--suites` 指定 suite。
- 无 arg 且无 `--scope` 时停止并要求补充；不默认选择 scope。
- `--module` / `--paths` / `--test` 仅用于 smart；branch/named 携带这些参数则停止。

主链委托 branch 时：失败须现场修到绿后再结束本 intent。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve modules | 约束 | 解析参数与范围；branch 要干净树 | 解析结果 | 2 | 停止并报告 |
| 2 | Select | 约束 | smart 选题；branch 定 suite；named 解析命令 | 命令列表 | 3 | 停止并报告 |
| 3 | Run | 脚本 | `mdf.py verify`（成败都进 4） | 运行结果 | 4 | 运行前缺前置则停 |
| 4 | Record | 脚本 | branch 成败均落盘；绿则勾选提交 | 证据或摘要 | 结束 | branch 可修/获批→3；其余失败停 |

## 术语与数据结构

### 范围与 module

- 读 `.mdf/modules.yaml`；smart 的 module 集合不得为空，缺失则停止。
- smart：当前 checkout 须为 branch；无需 `delivery.json`、`objectives.md` 或交付 slug。
  - 非交付 branch 的结果 `kind: unsupported`；Git、detached HEAD、版本命名或配置错误仍停止。
- named：从 suite shortcut 或 `--suites` 取得 suite 名；五固定入口由 modules 解析，
  真 named 按其 testing 文档 frontmatter 解析。名称未知、文档或命令缺失则停止。
- smart：`--paths` 命中 sourceset（非 ignore）并与 `--module` 合并。
- branch：全部 module；执行前 worktree 必须干净。
- bugfix 的 branch 验证：须已有 `suites.json` 关联 ≥1 已文档化 named suite。
  缺失则 `missing_delivery_suite`。

### 选题与命令

**smart**

选题范围按交付上下文确定；临时 branch 的起点 commit 由调用方记录。

| 上下文 | 选题范围 |
| --- | --- |
| 有交付上下文 | 相对 `delivery.json.start_commit` 的测试改动 |
| 无交付上下文 | 显式 `--paths` / `--module` 与已确认范围；独立修复引用 Bug 所需回归证据 |

1. 收集涉及 module 的 named suite 列表与上述范围内的测试改动。
2. 打开相关 `docs/system/testing/<suite>.md`。
3. Jev（或主 Agent）决定跑哪些 test/testcase；经 `--test` 传入。
4. 默认不整份跑 named suite。
5. lint/build/quick：未覆写的入口只跑 Resolve 得到的 module（`--module` /
   `--paths`）；顶层 `verification` 已覆写的入口仍跑该**整仓单命令**，
   不因 `--module` 缩小范围。

**branch**

- feature / bugfix / hotfix → smoke；release → release。
- 实际执行：全部 module 的 lint + build + quick + 上述套件，默认按 module
  **串行展开**；`modules.yaml` 顶层 `verification` 覆写的入口用单命令。

### 执行与失败处理

- CLI：`mdf.py verify --scope smart|branch|named ...`
- 遵守「测试失败工作流」：框架报告 → 单用例复测 → 修一个复测一个 → 再继续。
- 📌 本轮命令**无论成败**都进入 4 Record；不在本步内「修到绿才进 4」。
  - 需改测试门槛：先在 4 保存失败结果，再等待批准；确认后回 3 修复重跑。
  - 命令已运行后判为不可修：仍先进入 4 保存结果，再停止；运行前缺前置则直接停。
- branch 未绿且可修时：先完成 4 的失败落盘，再由 4 打回本步；在本步修实现
  （改测试须批准），提交相关路径并保持干净树后重跑 CLI，再次进 4。
  - 不回退假阶段、不发明对 converge 的过期检查。
- 修代码时**自行从架构师角度审视**修复是否合适（范围、边界、与设计一致性）。
  - ❌ 不因此强制重开 `$mdf code-review`。
  - 审视要点只在 4 于 branch 已绿时写入 `verification-report.md`（与摘要同文件）；未绿轮不写。
- 本 intent 内出现业务改动（实现/测试/验证配置）：提交或还原后须再跑本步并进 4。

### 记录与完成

- branch：无论成败均写入 `changes/unreleased/<slug>/verification-report.json`；
  **report**，非 gate；不含 commit / head；`all_passed:false` 时 CLI 仍失败。
  - 未绿且可修 → 回 3（提交后重跑）；未绿且阻塞 → 停止并报告。
  - 仅 `all_passed:true` 时：追加 `verification-report.md`（suite、报告路径、架构审视要点）。
    报告标题为 Verification Report，写明 scope: branch 与实际 suites；阶段仍为 verify branch。
    勾选 objectives 的 verify branch 并提交。
  - ❌ 未绿轮不得勾选 verify branch，不得把失败摘要当成通过证据。
- 普通主链完成条件：本 intent 内 branch 已绿并勾选提交；adhoc 按其 smart 专用条款完成。
  - ❌ 不以相对下游 intent 的过期审判或 commit 对齐作为本步通行证。
- adhoc smart：成败均保存 `verification-report.json`；主链前置为工作与 code-review 已勾。
  未改变业务内容且通过后，自勾 verify smart 并提交；其他 smart/named 不写 branch 证据、不勾选。
  通过读 stdout，失败读 stderr JSON；失败不宣称通过。
- quick 复现结论只在 branch 已绿写入 `verification-report.md` 时一并记录。
  - 不写 `code-review.md`（审查轮次的 quick 复现仍由 code-review 自记）。
