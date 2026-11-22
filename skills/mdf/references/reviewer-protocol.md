# 共用 Review 协议

## 执行边界

本协议供步骤 2 的审查与 CI 外部复核使用。派不出 subagent 时由主 Agent 审查，不得拒绝审查。

- 以最严苛的白盒测试专家视角审查实现代码和测试用例，主动挑战实现逻辑与测试的充分性。
- 以证据核实逻辑正确性与测试有效性，不因测试通过就认定实现正确。
- 交付步骤 2 的 reviewer subagent 与 CI reviewer 不修改审查对象，不运行 tests，不调用会落盘的 MDF CLI。
- 主 Agent 在 `--read-only` 或显式 `--against` 时调用 `review-context` 与 `review-report-check`。日志和报告在 checkout 外。subagent 不调用这些命令。
- 交付 reviewer 通过回复返回报告。派不出下一级 subagent 时就地审完，不得把未审查交回。
- reviewer 可以读取和搜索项目文件、读取 Git 对象；权限由调用方落实。
- 交付 controller 在派发前准备 lint、测量、验证报告，全部独立审查返回前不修改审查对象。
- `--read-only` 跳过修复与返工，不要求交付材料，不勾 objectives；worktree 必须 clean。有冻结 roster 时按 roster。没有 roster 则按总行数定人数；人数大于 1 才按模块相近度切开。
- 未审查不得写入 incomplete，也不得因此把 decision 写成 needs-review。diff 体积、path 数量、任务大小与派发失败同样不得。
- 下方 reviewers、owner、增量与 delivery 字段仅适用于交付模式；`--read-only` 使用独立报告 schema。
- 本地完整流程及修复窗继续按 [code-review](code-review.md) 执行。

## 上下文与范围

本节规定 controller 交付给各 reviewer 的固定输入。

| 字段 | 用途 |
| --- | --- |
| source、delivery_base | 交付身份与固定起点；默认 release 为上一正式版本 |
| review_base、review_head | 本轮实际审查范围；增量复核包括上轮问题 |
| policy_ref、rules_sha256 | 固定 target commit。指纹含协议版本号，不含协议全文 |
| merge_base、target_paths、target_diff | 两端共同祖先与 target 独有变化；用于合入影响分析 |
| context_sha256 | 本轮输入身份；每份报告必须一致 |
| roster、paths | 冻结人数、review strategy 与需覆盖路径 |
| artifacts、incomplete | 现有交付证据与缺项；缺项不能默认为通过 |

- 实现审查与 sourceset 求交后再应用 module ignore；文档与交付材料不进强制 paths，可读不禁。
- 显式 `--against` 与 `--read-only` 直接比较历史版本与当前 HEAD；worktree 必须 clean；配置与规则均来自当前 HEAD。
  - against 为完整基线 SHA，head 为当前 HEAD 完整 SHA；paths 与 diff 已过滤。
  - 仅 `--read-only` 在复核前核对 HEAD 与 context 指纹；变化后重建 context 并回步骤 2。进入过 Repair 或 Record 后不重建。
- 交付 CI 模式继续使用固定 source 配置和 target policy，保留 target 上下文与旧 findings。
- 同时读取必要上下文，不仅审 diff、标题或文件名。
- 审查正确性、验收覆盖、测试质量、code smell、架构合理性与非必要复杂度。
- MDF rule 与 project rule 原文均须传入；冲突时 project rule 优先。
- replicate 每人覆盖全部路径；partition 由 controller 切片，所有报告覆盖并集须完整。
- 单人覆盖全部范围；同一轮的审查者不共享彼此 findings。
- `.mdf/modules.yaml` 的 ignore、规模与拆分规则遵循固定策略和测量报告，不手工重复计数。
- 默认 release 不得因 child 已审而跳过上一正式版本以来的变化；独立 against 按指定历史版本与当前 HEAD。

## 独立报告

mode=against 使用 [独立报告 schema](../assets/templates/against-review-report.schema.json)，直接返回审查结果。

- 完整覆盖 paths，记录 against、head、rules_sha256 与 context_sha256。
- findings 仅列有静态证据支持的问题，包含 id、path、line、priority、trigger、impact、evidence。
- 必须审完全部 paths 才能出结论。无 P0/P1 为 pass；有阻断问题为 changes_requested。已审 finding 仍须人工判断时为 needs-review，且 findings 不得为空。
- 工具失败使用 error；changes_requested 必须有 finding；不因未运行 tests 自动降低优先级。
- incomplete 仅在 decision 为 error 时可以非空，且只记工具失败。不得写入尚未读完的 path。不将不存在的 MDF 交付材料列为缺项。
- 未审查不是合法 decision。diff 体积、path 数量、任务大小与派发失败都不得作为 incomplete 或 needs-review。
- 不要求独立 reviewer 份数、owner 裁定或旧 finding 表；修复后须 clean 提交，再重新完整审查。

## Findings 与裁定

本节只约束步骤 3 与 CI owner 的裁定。`--read-only` 不进入本节。未审查不得写成 needs-review。

1. reviewer 返回 id、path、line、priority、trigger、impact、evidence。
2. CI owner 汇总去重，逐项说明 accepted、rejected 或 needs-review 的证据和理由。
3. 需要新增复现 test、修改实现或无法核实的项交回开发侧 code-review intent。
4. 交回开发侧时沿用原优先级；复现、降级与最终修复按原 intent，不伪造运行结果。

| decision | 含义 |
| --- | --- |
| pass | 全部审查完整，已完成裁定，无采纳的 P0/P1 阻断项 |
| changes_requested | 存在已核实采纳的问题，等待开发侧处理 |
| needs-review | 已审项缺证据或需要人工决定。覆盖未完不是此结论 |
| error | reviewer、工具或报告处理失败 |

- CI owner 不按票数裁定；未完成裁定或等待复现不得 approve/merge。
- priority 使用 0–3；P0/P1 为本轮自动批准的阻断项，其他采纳项可作为建议。
- 增量报告逐项复核旧 finding：resolved、reopened 或 not_applicable，并给证据。
- reopened 旧项由原 reviewer 在 findings 保留原 ID、完整证据与原级别；缺项或未裁定时只能 needs-review/error。
- findings 可交回开发侧；范围、规则与份数符合原 intent 才可复用独立报告。
- CI 报告保存 SHA；交付终稿正文继续无 SHA，不互相覆盖。父 PR 返工备注按 code-review 的 Record 条款保留。
- 每轮报告保留固定 delivery_base；增量仅推进 review_base/head，首次 release 的后续轮也不能改变交付基线。

## 输出与执行器

本节只约束项目 CI controller 的启动方式。`code-review` 命令按「派发」执行；启动不了 reviewer 时由主 Agent 审查，不得未审完结束。

- schema 见 [CI 报告 schema](../assets/templates/ci-review-report.schema.json)。
- 交付 controller 先执行 `review-context`，再独立启动冻结人数份 Codex/Cursor CLI。
- controller 落盘 reviewer 回复；CI owner 接收全部报告后汇总为 schema 指定的最终 JSON。
- Codex 使用 `codex exec`；Cursor 使用 `agent -p`。两者按项目配置落实只读权限。
- Cursor 的 JSON envelope 先提取 result；必须为完整 JSON，不猜测或修补损坏输出。
- controller 执行 `review-report-check`，并核对 checkout、Git diff 及实际 head 未越界变化。
- 格式通过只表示协议完整；平台动作还须核对当前 head、规则、测试与项目 policy。
- approve、request changes、merge、notify 由后续持有平台凭据的步骤执行。
- 完整接入见 [CI 接入](ci-review.md)。
