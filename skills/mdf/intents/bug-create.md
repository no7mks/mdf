# Bug Create

完整读取 `intents/common.md`、`intents/clarify.md`、
`references/repository-contract.md` 与 `references/object-contract.md`。

## 决策树

```text
doctor → 允许正常流程？否：停止；是 → 手动 Bug 事实澄清 → clarify
→ 用户确认 open？否：继续澄清；是 → slug/ID → 写 open Bug → 展示结果
```

## 工作流（唯一执行契约）

1. **脚本**；解析 `REPO_ROOT` 并运行 `doctor`；证据：
   `normal_workflows_allowed: true`；通过 → 2；失败 → manifest 未就绪时提示
   `$mdf init`，其他 findings 报告后停止。
2. **约束**；接收用户手动提供的单个 Bug 事实；一次只问一个问题，澄清范围、关键事实
   与取舍。外部想法、当前聊天上下文或外部文档必须显式调用 `$mdf intake`；证据：确认的
   Bug 与采用范围；通过 → 3；失败 → 等待澄清。
3. **约束**；使用内部 clarify intent 按轮次澄清观察到的行为、期望行为、复现步骤、影响、
   所需回归证据、`found_in` 与 severity；证据：完整必填事实；通过 → 4；失败 → 必填事实
   仍无法确认时停止，不得写入任何对象。
4. **约束**；展示 Bug、边界和排除范围；证据：只有用户明确确认 open 才继续；通过 → 5；
   失败 → 回到 2 或 3。
5. **脚本**；为 Bug 提议并确认英文 ASCII kebab-case slug，使用 `make-id --type bug --slug`
   生成 ID 与规范化文件名，并以模板写入 `bugs/`，状态为 `open`；证据：open Bug；
   通过 → 6；失败 → 停止并保留现场。
6. **约束**；展示 open Bug、确认事实和排除范围；证据：会话摘要；通过 → 结束；失败 → 停止。
