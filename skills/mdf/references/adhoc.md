# Adhoc

`$mdf adhoc [<工作描述>]` 在临时 worktree 中连续完成一次小工作，直到本地收口。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 范围不明 ────→ [询问缺项]
                 ├──── 未就绪 ──────→ [停止并报告]
                 │
                 ▼ 目标与范围已定
┌──────────────────────────────────┐
│ 2 Prepare                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 启动或绑定失败 ────→ [保留现场并报告]
                 │
                 ▼ owner 已绑定
┌──────────────────────────────────┐
│ 3 Select                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 实际收口已完成 ────→ [报告并结束]
                 ├──── 身份或账本不符 ────→ [停止并报告]
                 │
                 ▼ 下一步骤已确定
┌──────────────────────────────────┐
│ 4 Execute                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 阶段完成 ────────→ 3 Select
                 └──── 失败或待确认 ────→ [按原阶段交接]
```

## 工作流（唯一执行契约）

读取 `references/common.md` 与 `references/delivery-contract.md`；本页专用条款优先于普通交付主线。
不执行 start 的 clarify、PRP 选择或 roster 确认。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve | 约束 | 核仓库、ready 与本次工作范围 | doctor、分支、工作描述 | 2 | 范围不明询问；其余停 |
| 2 | Prepare | 脚本 | 复用已有 adhoc，或自动命名并创建 owner worktree | 身份、路径、五项账本 | 3 | 保留现场并报告 |
| 3 | Select | 约束 | 核对五项账本并选首个未勾项 | checklist、实际 Git 结果 | 未完 4；已收口结束 | 身份或账本不符则停 |
| 4 | Execute | 约束 | 完成工作或委托原 intent，成功后自勾提交 | 阶段产物与提交 | 3 | 按原阶段交接 |

## 术语与数据结构

### 范围与启动

本节规定临时工作的授权、命名和工作区落点。

- 工作可以是代码、测试、文档、配置或其他已说明的需求，不绑定 PRP 或 Bug。
- 工作描述取自本次参数或已明确的对话上下文；只在缺少实际需求或边界冲突时询问。
- 显式 adhoc 授权完成五项步骤及必要本地提交、集成和收口。
  - objectives 内容、slug 与固定 roster 直接生成，不另做确认。
  - 目标变更、测试门槛批准及 fact 的确认仍沿用各 intent 规则。
- 运行 doctor 与 branch，要求 ready、`normal_workflows_allowed: true`。
  - 新建前检查源工作区 clean 与本地 develop 存在。
  - 不能把已有改动搬走或提交来满足 clean；失败保留现场。
  - 已有其他交付时先明确目标，不把其改动混入新任务。
- Agent 自行选与需求相关且不冲突的 slug，不要求用户指定格式或确认。
  - CLI 将 `--name` 规范化为材料目录可用的 slug；冲突时另选相关名称，不覆盖既有材料。
- 运行 `mdf.py start --repo <仓库> --kind adhoc --name <名称>`。
  - 从本地 develop 创建 `adhoc/<slug>` 与 `<repo-name>-worktrees/adhoc/<slug>`。
  - 不 fetch、不 push；有 origin 时沿用 start 的基线覆盖检查。
  - 固定 roster `0,0,1`，`needs_design: false`；不建立 qa/dev 角色树。
- CLI 写入并提交 `changes/unreleased/<slug>/delivery.json` 与 `objectives.md`。
  - 账本直接使用 `assets/templates/adhoc-objectives.md`，初始五项均未勾。
  - 不要求 design、converge、人工工作确认或额外的 start checklist 项。
- start 返回可选 hook 时按 [post-gitflow-start](hooks/post-gitflow-start.md) 处理，包括 pending rule。
- 按 common 的「切换工作区」绑定返回的绝对 owner 路径；后续只在该 worktree 工作。
  - 已有交付用 `delivery status` 取路径与 start_commit，缺树时停止，不重新 start。

### 五项账本与续办

本节用唯一 checklist 决定下一项工作。

objectives 的五项必须同序、完整；工作由 Agent 或用户实际完成后即可勾选。

| 清单项 | 执行与完成证据 |
| --- | --- |
| 工作 | owner 完成本次范围，核对成果与必要测试，提交并自勾 |
| code-review | 委托 `references/code-review.md`；1 人独立审查，终稿与自勾 |
| verify smart | 按下节委托 verify；通过的 smart report、自勾与提交 |
| fact audit/update | 按下节审阅，必要时更新；fact 确认、自勾与提交 |
| close-out | 按下节收口；Change、no-ff 合并、源分支删除与保留的 worktree |

- 默认从首个未勾项执行到实际收口；有效的已完成项不重复执行。
- `$mdf next` 在已启动 adhoc 上仅执行本页步骤 3–4 的一个账本项，然后返回。
  - 不新建 adhoc，不升级为连续执行。
- `$mdf deliver` 在已有 adhoc 上以本表替代普通选择表，每次完成一项返回其 Select。
  - 保留 deliver 原有模式、确认及完成核验规则；无 target 时不凭空新建 adhoc。
- 清单全勾仍须核对 finish 实际成功；仍在 adhoc 分支或上次 finish 失败时继续 close-out。
  - 不凭全勾宣称完成，不因正常 detached 状态重新 start。

### Smart 与事实

本节规定两项验收的范围、报告与返工规则。

- verify smart 前工作与 code-review 均须已勾，按 `references/verify.md` 执行 smart。
  - 相对 start_commit 收集改动，选择涉及 module 与测试；纯文档等无法映射 module 时使用全部 module。
  - 不改用 branch 或 smoke；CLI 成败均保存 `verification-report.json`，`scope: smart`。
  - 通过后自勾 verify smart 并提交；失败读取报告，修复后重验，不勾选失败步骤。
  - 验证期间改动实现、测试或验证配置时，退勾 code-review 及后续项，返回该项补审后再验。
- fact audit/update 在 verify smart 已勾后执行。
  - 先按 [pre-gitflow-finish](hooks/pre-gitflow-finish.md) 执行可选 hook；续办不重跑已执行 hook。
  - hook 触及实现、测试或验证配置时退勾 code-review、verify smart 与 fact 项，先补审补测。
  - 按 `references/fact-audit.md` 审阅 branch scope，基线为 start_commit。
  - 需更新时委托 `references/fact-update.md`，沿用其内部审阅；不新增 checklist 项。
  - 获得有效 fact 确认后保存 `fact-audit.md`，自勾 fact audit/update 并提交。

### Close-out 专用条款

本节由 adhoc 的最后一项或当前 adhoc 上的独立 close-out/finish 执行，替代普通 close-out 主线。

1. 读取 common 与 delivery-contract，运行 doctor、branch 和 delivery status，核对 ready 与 adhoc 身份。
   - 工作、code-review、verify smart、fact audit/update 须已勾，三份 report 已交且声称通过。
   - smart report 必须属于本分支且 `scope: smart`、`all_passed: true`；不做 commit 对齐审判。
   - code-review 终稿无 commit hash、无未解决项；fact 已确认。
2. 只读检查源与 develop 的实际合并工作区均 clean、无未完成 merge；有问题保留现场并停止。
   - 不清理、stash、reset、abort 或提交他人的改动；无关工作区不检查。
3. 若 develop 尚非 owner HEAD 的祖先，固定两端 commit，调用 `merge-no-ff` 将其集成到 owner。
   - 冲突按 close-out 的既定目标核实后尝试解决；语义不明时询问并保留现场。
   - 除仅非本交付 `docs/` 的增量外，退勾 code-review、verify smart、fact 与 close-out，返回本页 3。
   - 补审从集成前 HEAD 审增量；skip 时在 code-review 终稿追加说明，仍不写 commit hash。
4. 在同一材料目录用 `assets/templates/change.md` 补齐并提交 CHANGE.md。
   - `change_kind: adhoc`、`source_branch: adhoc/<slug>`、`proposals: []`，记录实际成果、outcomes 与证据。
   - 总结直接写入 Change；不要求 design 或 `delivery-summary.html`，不修改 PRP 状态或创建版本目录。
5. 核对 diff、Change、链接与报告，确认最终 HEAD 仍包含 develop；前进则回本节 2。
   - 本节不补跑 verify 或 fact；缺项回到对应账本项，不以旧报告替代未完成步骤。
   - 将 close-out 勾为 `[x]` 并提交，然后运行 `finish-gitflow --repo <owner>`。
   - deliver 的 auto-pilot 非 yolo 模式在 finish 前返回其步骤 6；确认后从 finish 调用续办。
6. 核实 no-ff 合入本地 develop、源分支已删除、owner worktree 已 detached 且仍保留。
   - 不 fetch、不 push、不打 tag；失败保留现场，不声称完成。
   - 保留目录供查看；只有用户明确要求删除时才删除，不删除 `.mdf/` 或 `docs/` 产出物。
