# Doc Create

不要自动 commit。

完整读取 `intents/common.md`、`intents/grill.md`、
`references/repository-contract.md` 与 `references/object-contract.md`。

1. 解析目标 Git 根 `REPO_ROOT` 后运行 `doctor`。只有
   `normal_workflows_allowed` 为 `true` 才继续；`manifest` 未就绪时提示
   `$mdf init`，其他 findings 则报告并停止。一次只创建一个 Proposal 或 Bug。
2. 一次只创建一个 Proposal 或 Bug。用户指定类型、标题和来源；中文标题时，Agent
   基于已确认语义提出英文 ASCII kebab-case slug，一次只问一个问题取得确认或修订。
   用 CLI `make-id --slug` 生成 ID 与规范化文件名，以相应模板在 `proposals/` 或
   `bugs/` 写入对象文件，初始状态为 `draft`。Proposal 必须链接其对应的
   `context/requirements/` 来源和 `context/planning/` MVP（若存在）。
3. 使用内部 grill intent 一次只澄清一个影响成稿的事实或取舍，并先查仓库证据。
   Proposal 收敛 Problem、Desired Outcome、Scope 和可验证 Acceptance
   Criteria；Bug 收敛 Observed/Expected Behavior、Reproduction、Impact、
   Regression Evidence Required、`found_in` 与 active severity。
4. 展示完整 draft、确认事实与排除范围。只有用户明确确认才转
   `ready`：先在 `draft` 状态运行 `targeted validation`，通过后再转换。失败时保留
   `draft` 和现场；普通对象不在此流程关闭，也不填 `fulfilled_in`/`fixed_in`。
