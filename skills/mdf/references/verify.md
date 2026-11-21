# verify

按 scope 运行验证；branch 要求交付分支，smart/named 不要求。
失败修复、增量复测和结果复用统一读取 [增量验证契约](verify-incremental.md)，所有 variation 均适用。

- **smart**：开发与 converge 使用（lint+build+quick + 改动测试/选题）。
- **branch**：独立主链 intent（在 code-review 之后）；失败先分诊已知 Bug，其余失败**现场修到绿**。
  - 默认 suite：feature/bugfix/hotfix → smoke；release → release。
  - 进度认 objectives 勾选；报告为落盘证据，不以 commit 对齐审判。
- **named**：按 `--suites` 跑指定 suite（五个必选入口、可选 coverage 或真 named）；不写 branch 证据。
  - 真 named 命令来自 testing 文档 frontmatter；可多命令，默串行，可 `parallel`。
- release 与 named 可含 playbook（Agent 执行的测试手册），pending 时读取 [Playbook 执行](verify-playbooks.md)。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve modules                │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 范围与调用上下文已确定
┌──────────────────────────────────┐
│ 2 Select                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 范围、配置或排除核验失败 ────→ [停止并报告]
                 │
                 ▼ 命令与适用续办参数已保存
┌──────────────────────────────────┐
│ 3 Run                            │
└────────────────┬─────────────────┘
                 │
                 ├──── 前置缺失或请求无法恢复  ────→ [停止并报告]
                 │
                 ▼ 本轮命令已执行（含失败）
┌──────────────────────────────────┐
│ 4 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 落盘失败 ───────────────────→ [停止并报告]
                 ├──── 新豁免已处理 ───────────────→ 3 Run（含非主链）
                 ├──── 无新豁免且主链可修/获批 ────→ 3 Run（修复并提交后）
                 ├──── 无新豁免且主链未绿阻塞 ─────→ [停止并报告]
                 ├──── 非主链无新豁免 ─────────────→ [按实际结果返回]
                 │
                 ▼ 主链已绿，尚不勾选
┌──────────────────────────────────┐
│ 5 Recheck                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 待审范围或原验证参数缺失 ────→ [停止并报告]
                 ├──── 增量审查未完成 ──────────────→ [保留现场并报告]
                 ├──── 原报告被覆盖或命令不匹配 ────→ 3 Run（原范围）
                 ├──── 审查修复又改业务内容 ────────→ 3 Run（原范围）
                 │
                 ▼ 必要复审完成且原范围报告匹配
┌──────────────────────────────────┐
│ 6 Tick                           │
└────────────────┬─────────────────┘
                 │
                 ├──── 勾选或提交失败 ────→ [停止并报告]
                 └──── 成功 ──────────────→ [返回调用方]
```

## 工作流（唯一执行契约）

adhoc 的主链执行 smart；Core 成败均保存 smart report，Agent 在步骤 6 完成验收后自勾 verify smart。

无账本 adhoc 按 [Adhoc 检查与事实](adhoc-change.md#检查与事实) 选择验证入口。
使用 adhoc-status 的材料目录，不要求或创建 checkbox；步骤 4 返回结果，由调用方完成必要补审补测。
本页下方的 adhoc 主链勾选和小 loop 条款仅适用于有账本交付。

开发或 code-review 内部 smart 不勾主链项；主链验证中修改业务内容则退勾 code-review 及后续项，按下方小 loop 完成增量复审。
人工 feature 的 objectives 项名为 verify smoke；执行 branch scope，沿用 feature
的 lint/build/quick/smoke 和 branch 报告要求，在步骤 6 自勾 verify smoke。
在该交付上 `$mdf verify smoke` 也按此 branch 主链解释，不走 named shortcut。


读取 `references/common.md` 与 `references/delivery-contract.md`。

入口：`$mdf verify [arg]`；arg 为 smart/branch/named 时按 scope 解析，其他值
作为 named suite 名。也可显式使用 `--scope smart|branch|named`；可选
`--module` / `--paths` / `--test`。

- 位置参数不与 `--scope` 同用；仅 `named` 可带 `--suites`。
- `verify named` 需通过 `--suites` 指定 suite。
- 无 arg 且无 `--scope` 时停止并要求补充；不默认选择 scope。
- `--module` / `--paths` / `--test` 仅用于 smart；branch/named 携带这些参数则停止。

主链委托 branch 时：按 [已知 Bug test 契约](known-bug-tests.md) 处理可豁免项，其余失败须现场修到绿。
完成必要增量复审后再结束本 intent；release 的失败不豁免。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve modules | 约束 | 解析范围、主链身份与已有续办上下文 | scope、调用方、module、适用 objectives | 2 | 停止并报告 |
| 2 | Select | 约束 | 保存原范围与左端点，核对现有排除并选命令 | 选题、排除核验、左端点 | 3 | 停止并报告 |
| 3 | Run | 脚本 | 首轮执行 CLI，后续增量复测；pending 委托 Playbook 执行，成败均返回 | 实跑结果与复用证据 | 4 | 缺前置则停；pending 失效转增量续办 |
| 4 | Record | 约束 | 分诊 Bug 并处理新豁免 | 报告、关联、diff | 新豁免 3；主链绿 5；非主链按实际结果返回 | 主链可修/获批 3；其余停止 |
| 5 | Recheck | 约束 | 判净变化；必要时委托 1 人增量 code-review | 增量范围、复审及修复结果 | 无新业务改动且报告匹配 6；修复改业务或报告不符 3 | 缺范围或复审未完成则停止 |
| 6 | Tick | 约束 | 核原验证通过与必要复审完成，自勾并提交 | 通过报告、复审证据、勾选与提交 | 返回调用方 | 保留现场并报告 |

## 术语与数据结构

### 范围与 module

本节解析调用上下文，不因退出码或 scope 名称独自推断主链进度。

- branch 是主链；人工 feature 的 verify smoke 仍映射为 branch。
- adhoc smart 由主链清单委托，或独立调用且工作、lint、code-review 已勾时，作为主链。
- 不满足上述主链条件的 smart（含开发、converge、code-review、fix、bug close 内部调用），以及 named 都不进入步骤 5–6。
- 已打开的 verify 小 loop 优先恢复：code-review 退勾表示待复审，不表示应先离开 verify。
- 步骤 2 先保存 HEAD 和原验证请求，再按 known-bug-tests 的预检核对并恢复失效排除，最后选命令。
  每次修复前保留最早尚未复审的左端点；预检改动也纳入复审。
- 原验证命令指固定 scope/模块/选题的请求；首轮与增量结果共同覆盖该请求，每次 Run 记录实际执行和复用范围。
- 已批准的验证配置变更后，更新实际命令基准，按增量验证契约补测受影响 case；未受影响的通过结果继续复用。

- 需要修复时，在已有 code-review 草稿记录来源 verify、原 scope/选题、左端点和待修绿状态。
- 同时在 objectives 的非 checklist 备注保留父 verify 的原命令、scope/选题与左端点；该备注只用于恢复，不是进度 gate。
- 子审查覆盖 code-review 终稿时保留父 verify 备注；步骤 6 完成小 loop 后才清理该备注。
- 这里只清理本轮 verify 备注；不得删除父 PR 返工备注，补验完成后仍按父流程返回原 PR。
- 新会话恢复先按备注恢复原请求与实跑/复用证据，只补失败、受影响或缺失范围，再续办未齐复审。
  原范围/参数缺失则停止，不猜测验收全集。


- 读 `.mdf/modules.yaml`；smart 的 module 集合不得为空，缺失则停止。
- smart：当前 checkout 须为 branch；无需 `delivery.json`、`objectives.md` 或交付 slug。
  - 非交付 branch 的结果 `kind: unsupported`；Git、detached HEAD、版本命名或配置错误仍停止。
- named：从 suite shortcut 或 `--suites` 取得 suite 名；固定入口与可选 coverage 由 modules 解析，
  真 named 按其 testing 文档 frontmatter 解析。名称未知、文档缺失或 command/playbook 均缺失则停止。
- smart：`--paths` 命中 sourceset（非 ignore）并与 `--module` 合并。
- branch：全部 module；dirty 时仍执行验证且不更新 clear commit。主链先提交本轮改动，以记录通过的 commit。
  有 playbook 的 branch 用 `delivery complete-stage --stage verify` 提交报告后记录 clear commit；增量汇总不更新该记录。
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

步骤 4 先核落盘，再处理新豁免；有新豁免优先回步骤 3 核对成员并增量补验，无新豁免才按主链/非主链分流。
非主链也须完成补验与结果汇总再返回。
失败先按 [已知 Bug test 契约](known-bug-tests.md) 精确匹配已有 `open` Bug 的关联 failing tests。
空关联、未命中关联或本次失败与关联缺陷不一致时不得豁免。
临时移除仅限 quick、smoke；其余检查通过后视为 verify 通过，并明确记录豁免项。

- CLI：`mdf.py verify --scope smart|branch|named ...`
- 结果为 `verify-pending`，或恢复已有 pending 时，读取并执行 [Playbook 执行](verify-playbooks.md)。
  - 子流程成功或测试失败均回步骤 4；pending 失效转增量续办，原请求无法恢复时停止，不勾选。
  - 多个 named suite 须全部完成；单个 suite 的 `all_passed` 不代表原请求整体通过。
- 遵守「测试失败工作流」：框架报告 → 单用例复测 → 修一个复测一个 → 补测受影响 case 并复用其余通过结果。
- 📌 本轮命令**无论成败**都进入 4 Record；不在本步内「修到绿才进 4」。
  - 已知 Bug 的精确成员移除与恢复按专门契约执行；其他需改测试门槛：先在 4 保存失败结果，再等待批准；确认后回 3 修复重跑。
  - 命令已运行后判为不可修：仍先进入 4 保存结果，再停止；运行前缺前置则直接停。
- 主链未绿且可修时：先完成 4 的失败落盘，再由 4 打回本步；在本步修实现
  （专门契约之外的改测试须批准），提交相关路径并保持干净树后增量复测，合并实跑与复用证据，再次进 4。
  - 不回退假阶段、不发明对 converge 的过期检查。
- 修代码时**自行从架构师角度审视**修复是否合适（范围、边界、与设计一致性）。
  - 主链修绿改了代码时，必须按下方小 loop 委托 1 人增量 code-review。
  - 审视要点只在 6 于 branch 已绿时写入 `verification-report.md`（与摘要同文件）；未绿轮不写。
- 本 intent 内出现业务改动（实现/测试/验证配置）：提交或还原后回本步评估影响，只补测所需范围并进 4。

### 记录与完成

- branch：无论成败均写入 `changes/unreleased/<slug>/verification-report.json`；
  **report**，非 gate；不含 commit / head；`all_passed:false` 时 CLI 仍失败。
  - PR mode 的 release/hotfix 候选材料已进入 `changes/<version>/` 时，报告写回该版本目录，不新建 unreleased 副本。
  - 未绿且可修 → 回 3（提交后增量复测）；未绿且阻塞 → 停止并报告。
  - 仅 `all_passed:true` 且步骤 5 完成时，在步骤 6 追加 `verification-report.md`（suite、报告路径、架构审视要点）。
    报告标题为 Verification Report，写明 scope: branch 与实际 suites；阶段仍为 verify branch。
    完成下方主链小 loop 后，勾选 objectives 的 verify branch 并提交。
  - ❌ 未绿轮不得勾选 verify branch，不得把失败摘要当成通过证据。
- 普通主链完成条件：本 intent 内 branch 已绿且小 loop 完成并勾选提交；adhoc 按其 smart 专用条款完成。
  - ❌ 不以相对下游 intent 的过期审判或 commit 对齐作为本步通行证。
- adhoc smart：成败均保存 `verification-report.json`；主链前置为工作、lint 与 code-review 已勾。
  必要复审完成且通过后，在步骤 6 自勾 verify smart 并提交；其他 smart/named 不勾主链项。
  CLI 通过读 stdout，失败读 stderr JSON；增量执行另核汇总与来源，失败不宣称通过。
- smart 可用 `--report-file <仓库内路径>` 将成败结果改写到独立文件，保留默认报告；路径不得越出仓库或含符号链接。
  incremental-integration 必须使用独立报告；branch/named 不接受该参数。
- quick 复现结论只在 branch 已绿写入 `verification-report.md` 时一并记录。
  - 不写 `code-review.md`（审查轮次的 quick 复现仍由 code-review 自记）。

### 主链 review/verify 小 loop

本节适用于 branch、人工 feature 的 verify smoke 与 adhoc 的主链 smart，独立调用和 deliver 均执行。

1. 步骤 2 保存的原命令与左端点沿用到本轮复审完成；失败先在 4 核报告，再修复并提交后回 3 增量复测。
2. 步骤 5 修绿后检查相对左端点的净变化，核对 HEAD 及 staged/unstaged/untracked，不能只看已提交 diff；工具生成的业务改动也须纳入。
3. 实现、tests、fixtures 或验证配置有改动时，提交相关路径，退勾 code-review、验证及后续项，并保存待复审草稿。
4. 修绿后将草稿标明待复审，固定左端点到当前 HEAD；委托 `references/code-review.md` 做 1 人增量审查，不改冻结 roster。
5. 增量审查通过后，记录本轮已审 HEAD，推进操作左端点并更新、提交续办备注；交付起点不变，未完成审查不得推进。
6. 增量审查未改业务且原报告仍匹配原 scope、命令与选题时，沿用刚完成的通过报告进入 6。
7. 审查修复改了业务，或报告被覆盖/不匹配时，回 3 恢复证据并增量补测；仅对已审终点后的新业务改动再次复审。

- 验证未改代码时不增加 reviewer；报告、objectives 和纯事实文档不触发复审。
- 原 scope 与选题固定，不以 smart 代替 branch；实跑与复用结果须共同覆盖父阶段的完整验收范围。
- code-review 内部 smart 留在既有修复窗，不递归委托本 loop，也不勾主链验证。
- adhoc 子 smart 可覆盖同路径报告；步骤 5 核对原参数与实际报告，不能把子流程的部分验证冒充原主链结果。
- 恢复时先读草稿中的原 scope/选题、左端点、待修绿/待复审状态与问题清单；缺少任一必要上下文则停止，不猜测起点。
- 通过报告可先落盘，但小 loop 未完成时不得勾选主链验证或进入 fact。
- 续办备注更新或提交失败时保留现场并停止，不推进左端点或勾选验证。
- 终止条件：相关审查完成，失败和受影响 case 已通过，其他成员均有有效复用证据。
  原请求缺少哪些证据就补哪些；全部缺失时才补完整首轮。
- 主链 verify 中的架构自查继续保留，不能替代该增量独立审查。

### 可选 coverage

coverage 是与 lint/build 同级的可选验证入口，不属于 quick/smoke/release 的 test 成员集合。

- `$mdf verify coverage` 等同 `verify --scope named --suites coverage`，读取 modules.yaml 的完整 coverage 配置。
- 未配置时返回 configured: false，明确记录未配置；配置后所有 targets 均须达标。
- 项目 command 写入本次 `$MDF_REPORT_DIR/coverage.json`，MDF 保存 summary 与完整原始日志。
- coverage 使用统一 metrics JSON，不要求 JUnit；不自动加入 smart、branch 或 code-review 的内部 smart。
- 自动检查点仅为实际执行的 feature/release converge；定义、targets 与报告接口见 repository-contract。
