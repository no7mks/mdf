# 无账本 Code Review

本页供普通 branch 的独立 code-review 与无账本收口委托共用；只完成审查及必要修复验证。

## 入口与范围

先确定 branch 身份、实际改动与调用边界，再准备审查。

1. 读取 common.md，核 Git 根与 manifest ready；运行 branch，先识别内部角色及 backmerge 的所属 workflow。
2. feature、bugfix、release、on-demand-release、hotfix 沿用专用流程；master/main/develop/planning 不走本页。
   材料缺失时说明分类与缺项。`--read-only` 不进入本页。单独 `--against` 只覆盖左端点，不把本页改成只读。
3. worktree 必须 clean；按 common 处理本次相关未提交成果；无法隔离时停止，不遗漏未提交工作或提交他人改动。
4. 运行 `adhoc-status --repo <owner>`，使用返回的 material_mode、path、range、paths。
   ledger 返回有账本 code-review；损坏账本停止，不绕过或补造 delivery/objectives。
5. 报告 kind、material_mode、base、target 与下一步；无待审改动时结束，不生成 Change 或删除 branch。

- 收口委托沿用调用方冻结的 base、head 与 policy_ref；不得重新追随移动的 target。
- 独立调用使用 status 的 range.base，固定当前 HEAD；policy_ref 为本次解析的目标 tip。
  local 使用本地 develop，PR mode 使用 origin/develop；独立 review 不 fetch、merge 或 squash。
- 目标缺失、范围歧义或包含归属不明工作时停止说明，不猜测基线。
- 已有 Change evidence.range 时沿用固定范围；没有时仅在本轮草稿保存端点，不为 review 创建 Change。
  新调用缺少可恢复端点时重新解析并完整审查，不凭旧终稿推断增量范围或收口检查已完成。
- 恢复未结束的父 PR 时，先读取其备注与原验证请求，再按原范围续办。
- 不读写 roster 配置；独立调用不接受 roster strategy/model 覆盖参数。人数按 code-review「派发」的无 roster 规则，不固定 1 人。

## 工作流（唯一执行契约）

本流程复用 code-review 的审查和修复规则，不进入其他交付阶段。树形：not-tree。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Lint | 约束 | 按 lint.md 检查实际范围，无 checkbox | lint 报告 | 2 | 修复后重验；不可修则报告 |
| 2 | Review | 约束 | 按 code-review「派发」审完全部范围；派不出则主 Agent 审 | 覆盖全部范围 | 3 | 未覆盖留在 2 |
| 3 | Repair | 约束 | 主 Agent 裁定、修复并验证 | 裁定与实际验证报告 | 4 | 可修留3；需决定则报告 |
| 4 | Record | 约束 | 保存终稿，保留父流程恢复备注并提交 | 终稿、备注与提交 | 返回调用方 | 未完成不声称通过 |

### 审查与修复

审查内容、证据和复核标准与有账本 code-review 相同。

- 读取 [Review 协议](reviewer-protocol.md) 与 code-review 的「独立审查」「缺陷复现」「汇总、修复与复核」条款。
  使用相同 reviewer opening、范围过滤、finding 裁定与 regression test 要求。
- 从固定目标 policy_ref 加载项目 rule 与 AGENTS.md，分别传入 base、head、policy_ref、实际工作与 lint 报告。
  不把固定 base 当作最新目标。显式 `--against` 只覆盖左端点；policy 仍取当前 HEAD。`--read-only` 不进入本页。
- lint 修复提交后固定本轮 review_head，再派 reviewer；base 与 policy_ref 保持原值。
- 本轮修复沿用原 review_head 与 findings；修复窗结束后新改动才进入增量复核，人数仍按无 roster 的行数规则。
- 修复实现、测试或验证配置后，按 [Adhoc 检查与事实](adhoc-change.md#检查与事实) 补验。
  验证失败继续修复；无账本 local close-out 委托也由本流程完成，不套用有账本 close-out 的交接限制。
- 未完成父 PR 的原验证请求仍须履行；本次修复验证不冒称整个 PR 返工已完成。

### 报告与返回

报告保存在 status 返回的材料目录，不创建账本或收口材料。

- 按 code-review 的终稿内容要求写 code-review.md，正文无 commit hash；尚未结束的父 PR 备注单列保留。
  备注中的 SHA 仅恢复父流程，不代表审查通过；由 pr 在补审补测与 fact 完成后清除。
- 有未完成问题或缺少证据时保留草稿，报告实际状态；通过后提交终稿，不创建或勾选 objectives。
- 独立调用到此结束，不执行 fact、pr、close-out、hook 或 Gitflow；内部委托返回原调用方。
