# Bug 的 failing test 关联、临时移除与恢复

本契约供所有 Bug 创建入口、verify 已知失败分诊、fix 和所有写入 Bug `fixed` 状态的流程使用。
树形：not-tree。调用方按事件执行本契约，不另启动交付 intent。

## 工作流（唯一执行契约）

调用事件为 create、verify-select、verify-record 或 restore；调用方先确认写入分支与当前 checkout。
只执行当前事件的条款，不提前执行调用方后续阶段，不递归调用 verify。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve event | 约束 | 确认事件、Bug 与 test 范围 | 调用方、事件、目标路径 | 2 | 不明则停止并澄清 |
| 2 | Inspect links | 约束 | 核创建输入或既有关联、排除有效性 | 输入、关联、状态、选题 | 3 | 既有记录不明或无法恢复则停 |
| 3 | Apply event | 约束 | 按事件取红灯、预检、移除或恢复 | diff、命令、对应证据 | 4 | 缺事实则停；空关联待用户确认 |
| 4 | Validate result | 约束 | 核本次事件证据与返回位置 | 事件表的证据与去向 | 5 | 可修回 3；其余停止并报告 |
| 5 | Return result | 约束 | 保存关联与证据，返回调用方继续原阶段 | 持久记录、实际结果 | 返回调用方 | 写入失败保留现场并停止 |

## 术语与数据结构

### 调用事件

父流程在对应阶段调用本契约；关联内容先作为草稿，父流程分配 ID 后再随对象落盘。

| 事件 | 操作与证据 | 返回位置 |
| --- | --- | --- |
| create | 准备关联、实际红灯或明确空关联确认；不自行分配 ID、创建对象 | 创建入口继续 Confirm/Create |
| verify-select | 核全部既有 Bug 临时排除，恢复失效项；无失效项则 no-op | verify 步骤 2 选命令，提交相关改动后进 3 |
| verify-record | 核本轮失败，处理新豁免；无新豁免则返回原失败结果 | 新豁免回 verify 3；否则由 verify 4 分流 |
| restore | 恢复全部关联 test 并取得通过证据；不自行写 fixed | fix 的 Record 或直接修复调用方标记状态 |

- verify 的实际 CLI 运行和报告由父步骤 3–4 完成；本契约不另开 verify intent。
- 创建对象、标为 fixed 与提交由父流程执行；下文列出其必须验收的顺序，不重复执行父步骤。

### 创建时建立关联

每个 Bug 创建时必须显式记录 failing test 关联，默认至少一条；允许复用或新增 test。

1. 先按 common 的写入归属确认目标 checkout；在该 checkout 对照观察行为与期望行为，复用已有 test，或新增专用于该缺陷的回归 test。
2. 实际运行每条待关联 test，取得针对该缺陷的断言失败；不在创建阶段修改生产实现。
3. 在 Bug「所需回归证据」的「关联 failing tests」子节逐条记录身份、命令和失败证据。
4. 展示关联清单并完成创建确认，将新增 test、Bug 和必要的选题配置一起提交。

- 创建 Bug 已授权新增复现 test；无需为了新增 test 再申请一次批准。
- 导入错误、编译失败、环境故障不算有效 failing test；通过的 test 不能充当红灯关联。
- 新 test 先确定正常应归属的 suite；临时移除前记录该成员关系，修复后按此恢复。
- 若无法取得有效 failing test，可请求用户明确允许空关联；未确认则不得创建 Bug。
  - 空关联写明 `关联 failing tests: []`、原因，以及用户确认的时间与内容。
  - 一般的创建确认、静默、confidence 或 `--yolo` 均不能代替空关联的明确确认。
- 空关联只允许记录 Bug，不提供 verify 豁免，也不免除 fix 的有效红灯要求。
- 后续新增关联同样须运行取得失败证据；补齐后保留空关联确认历史。
- bug create、intake、jot promote 与联调委托创建均执行本节，不因入口不同省略关联。

### 适用边界

仅允许已有 `open` Bug 对应的精确 test 暂时退出 quick、smoke。

| 条件 | 处理 |
| --- | --- |
| quick、smoke 的失败精确命中已有 `open` Bug 的关联 test | 核对失败依据、移除对应成员并增量补验；其余检查通过后 verify 通过 |
| `fixed` Bug 对应 test 再次失败 | 不豁免；重新确认缺陷与 Bug 状态，不自动改回 `open` |
| Bug 为 `closed`、`rejected`，或没有对应 Bug | 不豁免，按调用方原失败流程处理 |
| release、其他 named suite 或显式点名 test 失败 | 保留执行并阻断，不应用 quick、smoke 的豁免 |
| lint、build、coverage、环境故障、缺失或无效报告 | 不豁免，按原失败规则处理 |

- verify 以已记录关联为入口：module、文件路径与 runner test ID 必须精确匹配。
  同名 test 或参数化的其他实例不算命中；还须核对本次失败与关联缺陷一致。
- 先用 `list --type bug --status open` 定位候选，再读取候选正文；歧义时停止并请求澄清。
- 未关联或关联为空的失败不豁免；不在 verify 中凭语义相似自动补关联或创建 Bug。
  先按创建关联规则补充证据，再重新判断；不能用一个已知失败覆盖同轮的未知失败。
- 本契约授权精确调整 quick、smoke 的成员及恢复，不需逐次申请改测批准。
  - 修改断言、预期、fixture 或其他验证门槛仍按原批准规则处理。

### 持久记录

关联与临时移除共用 Bug 正文「所需回归证据」下的「关联 failing tests」清单，不新增 frontmatter 字段。

- 该子节包含唯一 `mdf-test-links` fenced block，内容为 JSON 列表；每项对应一个精确 test。
- 每项必须有 `module`、`file`、`test_id`、`suites`、`state`；其余证据按下表写在同节正文中。
- `suites` 为正常成员关系的 suite 名列表；`state` 为 `active`、`removed` 或 `restored`。
- 空关联的 block 为 `[]`，同时保留用户确认记录；不能省略清单或写未确认占位值。

每个关联 test 独立记录以下信息；移除方式在实际移除时补齐，不能等到 verify 失败才首次建立关联：

| 信息 | 要求 |
| --- | --- |
| test 身份 | module、仓库相对文件路径、runner 的精确 test ID；参数化实例需消歧 |
| 对应依据 | 完整 Bug ID、复现命令与退出状态、失败断言、复现条件与原始失败报告路径 |
| 原成员关系 | 正常应属于哪些 suite；新 test 创建时确定，不得遗漏其 quick、smoke 归属 |
| 移除方式 | 修改的选题配置或 marker 路径、精确排除项、恢复动作 |
| 独立执行 | 不受 quick、smoke 排除影响的点名命令，以及 release 仍会选中它的依据 |
| 记录状态 | `active`（已关联未移除）、`removed` 或 `restored`；恢复后保留关联与验证证据 |

- 同一 Bug 内同一 test 只保留一条关联；再次遇到时复用，不重复添加或移除。
- 无法唯一定位 test、保存原成员关系或保证独立执行时，不得豁免。
- test 重命名或移动时同步更新身份与恢复方式，不能遗留无法恢复的排除项。

### verify 处理

verify 在 Select 阶段先检查所有现有 Bug 临时排除项，再运行验证；失败后在 Record 阶段处理新的可豁免项。

- 对照 runner 的 Bug 临时排除项及 Bug 的 `removed` 记录，核对 test 身份、关联和当前 Bug 状态。
- 常规 suite 成员筛选不属于本预检；不因其没有 Bug 关联而删除或改写。
- 仅保留有有效 `open` Bug 关联的排除；Bug 变为 fixed/closed/rejected、已归档或关联失效时恢复成员。
- 恢复不要求 test 已通过；恢复后失败按当前状态正常处理，不继续享受旧豁免。
- 找不到原成员或无法判定排除归属时停止，不凭猜测删除配置，也不跳过检查。
- 状态变更、归档与 Git merge 后同样检查；没有新的 test 失败也不能省略。
- 此预检发生的选题修改纳入父 verify 的影响分析与主链增量复审，补验范围按 [增量验证契约](verify-incremental.md)。

1. 读取原始报告，以精确 test 身份查找已有 `open` Bug 的关联，核对本次失败依据。
2. 将命中关联的记录标为 `removed` 并补齐排除与恢复方式；按 runner 选题从 quick、smoke 排除。
3. 保留 test 源码和断言；确认 release 与显式点名执行仍选中该 test。
4. 提交本次记录与选题改动，核对成员变化并补测受影响 case，复用未受影响的通过结果。
5. 其余检查通过后，记录「通过，含已知 Bug 临时移除」及 Bug/test/报告引用。

- 排除使用 deselection 或 suite 成员筛选；不得用全局 skip、xfail 或删除 test 实现。
- release 必须独立包含被移除的 test，不能仅复用已过滤的 smoke 选题。
- 全部成员获豁免导致空 suite 时，按下节提交 collection 证据；普通空报告仍失败。
- 不得伪造通过 test；全豁免报告保留 `tests: 0`、`passed: 0` 与 `fully_exempted: true`。
- 不覆盖原始失败报告，不把原失败命令的退出码或 `all_passed: false` 改写为通过。
- 主链仍完成 verify 的增量 review 小 loop；选题配置变化属于需复审的业务改动。
- 非主链也须增量补验并返回真实结果；不以有 Bug 记录直接跳过其他检查。
- 最终报告逐项列出临时移除；不得将未执行的 test 声称为已通过。

### 全豁免空 suite 的报告

项目 runner 在本次 `$MDF_REPORT_DIR` 写 `empty-suite.json`，Core 校验后才接受空 quick/smoke。

- JSON 对象字段为 `suite`、`collected`、`excluded`；仅适用于本轮实际执行的 quick 或 smoke。
- `collected` 是应用 Bug 排除前、其他正常选题后收集的完整身份列表，必须非空且无重复。
- 身份包含 `module`、仓库相对 `file` 与精确 `test_id`；`excluded` 每项另含 `bug`，为 active Bug 相对路径。
- `excluded` 的身份集合须与 `collected` 完全相等；每项须命中该 open Bug 中当前 suite 的 removed 关联。
- 保留本轮空 JUnit；命令须正常退出 0。runner 的 no-tests 状态只能在 collection 成功且全部豁免时转为 0。
- 未识别的退出状态、collection 错误、超时、缺报告或无效证据仍失败；不能统一忽略非零退出。
- runner 若尚不支持该报告，Agent 先修改项目的持久 runner adapter，验证正常收集与故障分流，再重跑。
- Core `execution/empty_suite.py` 做确定性证据校验；失败不得手改 verification-report 的通过字段。
- 该证据不适用于 release、其他 named suite 或显式点名 test；部分豁免的剩余 test 须有实跑或有效复用证据。

### fix 恢复

恢复在修复完成并标为 `fixed` 之前执行，不等待 bug close。

1. 读取全部关联 test，用不受排除影响的点名命令确认有效红灯；空关联先补 test 与关联。
   仅修复遗漏的成员恢复且 test 已通过时，不修改生产实现，直接核对原红灯证据并恢复。
2. 修复实现，使全部关联 test 及该 Bug 所需回归证据通过；不使用本 Bug 豁免取得绿灯。
3. 逐条核对全部关联 test；已移除的恢复原成员关系，未移除的保留正常成员关系。
   清除该 Bug 的精确排除项；保留其他 test 的排除项。
4. 核对 runner 选题确实包含恢复的 test，并补测 quick、smoke 中受影响的 case，复用未受影响的通过结果。
5. 完成 fix 原有 smart 验证；已被同次验证完整覆盖的检查复用报告，不重复运行。
6. 将记录改为 `restored`，保存成员核对与通过证据，再把 Bug 标为 `fixed` 并一起提交。

- 同一 test 若还关联其他 open Bug，也须实际通过并恢复；无法恢复则本 Bug 不能标为 `fixed`。
- 恢复验证失败则保留现场、继续修复或报告阻塞，不得标为 `fixed`。
- 所有写入 `fixed` 的流程均须满足本节，包括交付分支上的直接修复。
- `fixed` 对象若仍有有效排除项，不满足修复完成条件；报告不一致并补齐恢复。
- bug close 核对已完成恢复；发现遗漏则停止并交给 fix 补齐，不以排除后的绿报告作复现证据。
