# Doc Create

不要自动 commit。

完整读取 `intents/common.md`、`intents/grill.md`、
`references/repository-contract.md` 与 `references/object-contract.md`。

1. 解析目标 Git 根 `REPO_ROOT` 后运行 `doctor`。只有
   `normal_workflows_allowed` 为 `true` 才继续；`manifest` 未就绪时提示
   `$mdf init`，其他 findings 则报告并停止。一次只创建一个 Proposal 或 Bug。
2. 用户指定 Proposal/Bug 类型与 slug；缺失或歧义时一次只问一个消歧问题。用 CLI
   `make-id` 生成 ID 与规范化文件名，以相应模板在 `proposals/` 或 `bugs/` 写入对象
   文件，初始状态为 `draft`。
3. 使用内部 grill intent 一次只澄清一个影响成稿的事实或取舍，并先查仓库证据。
   Proposal 收敛 Problem、Desired Outcome、Scope 和可验证 Acceptance
   Criteria；Bug 收敛 Observed/Expected Behavior、Reproduction、Impact、
   Regression Evidence Required、`found_in` 与 active severity。
4. 展示完整 draft、确认事实与排除范围。只有用户明确确认才转
   `ready`：先在 `draft` 状态运行 `targeted validation`，通过后再转换。失败时保留
   `draft` 和现场；普通对象不在此流程关闭，也不填 `fulfilled_in`/`fixed_in`。
