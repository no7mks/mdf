# Doc Create

完整读取 `intents/common.md`、`intents/clarify.md`、
`references/repository-contract.md` 与 `references/object-contract.md`。

## 决策树

```text
doctor → 允许正常流程？否：停止；是 → 手动内容澄清 → 对象确认 → clarify
→ 用户确认 draft？否：继续澄清；是 → slug/ID → 写 draft → 展示结果
```

## 工作流（唯一执行契约）

1. **脚本**；解析 `REPO_ROOT` 并运行 `doctor`；证据：
   `normal_workflows_allowed: true`；通过 → 2；失败 → manifest 未就绪时提示
   `$mdf init`，其他 findings 报告后停止。
2. **约束**；接收用户手动提供的单个 Proposal 或 Bug 的事实；一次只问一个问题，
   澄清类型、范围、关键事实与取舍。外部想法、当前聊天上下文或外部文档必须显式调用
   `$mdf intake`；证据：确认的对象与采用范围；通过 → 3；失败 → 等待澄清。
3. **约束**；检查对象类型与独立交付边界；偏差建 Bug，待实现意图建 Proposal；
   一次不得创建多个对象；证据：唯一对象；通过 → 4；失败 → 回到 2。
4. **约束**；使用内部 clarify intent 按轮次澄清成稿必要事实；Proposal 收敛
   Problem、Desired Outcome、Scope、可验证 Acceptance Criteria；Bug 收敛
   Observed/Expected Behavior、Reproduction、Impact、Regression Evidence Required、
   `found_in` 与 active severity；证据：完整必填事实；通过 → 5；失败 → 必填事实仍无法确认时停止，不得写入任何对象。
5. **约束**；展示对象、边界、排除范围、Proposal 依赖；`depends_on` 仅列直接依赖的
   draft、ready 或 closed + fulfilled Proposal ID；证据：只有用户明确确认 draft 才继续；
   通过 → 6；失败 → 回到 2 或 4。
6. **脚本**；为对象提议并确认英文 ASCII kebab-case slug，使用 `make-id --slug`
   生成 ID 与规范化文件名，并以模板写入 `proposals/` 或 `bugs/`，初始状态为 `draft`；
   证据：draft；通过 → 7；失败 → 停止并保留现场。
7. **约束**；展示 draft、确认事实、排除范围和依赖；证据：会话摘要；通过 → 结束；
   失败 → 停止。后续
   显式调用 `$mdf doc review`，经 draft targeted validation 后转
   `ready`；不得关闭普通对象或填写 `fulfilled_in`/`fixed_in`。
