# Doc Create

不要自动 commit。

完整读取 `intents/common.md`、`intents/grill.md`、
`references/repository-contract.md` 与 `references/object-contract.md`。

1. 解析目标 Git 根 `REPO_ROOT` 后运行 `doctor`。只有
   `normal_workflows_allowed` 为 `true` 才继续；`manifest` 未就绪时提示
   `$mdf init`，其他 findings 则报告并停止。
2. 接收一句话、当前聊天上下文或外部文档作为来源。来源只用于本次创建；除非用户
   明确要求保留，否则不得复制、归档或链接到仓库。一次只问一个问题，确认来源采用
   范围及尚不明确的关键事实或取舍。
3. 根据来源与仓库证据判断对象类型和数量。一个来源可同时包含已观察到的行为偏差和
   待实现意图，分别创建一个 Bug 和一个或多个 Proposal；多个 Proposal 按可独立
   交付的范围拆分。
4. 使用内部 grill intent 按轮次澄清影响成稿的事实或取舍。Proposal 收敛
   Problem、Desired Outcome、Scope 和可验证 Acceptance Criteria；Bug 收敛
   Observed/Expected Behavior、Reproduction、Impact、Regression Evidence Required、
   `found_in` 与 active severity。必填事实仍无法确认时停止，不得写入任何对象。
5. 展示拟创建的完整对象清单、每项边界、排除范围和 Proposal 依赖。Proposal 的
   `related` 只列当前对象直接依赖的 draft/ready Proposal ID；不得记录来源、Bug、
   ADR、已关闭 Proposal 或无依赖的同批对象。只有用户明确确认清单才继续。
6. 对每个对象基于已确认语义提出英文 ASCII kebab-case slug。用户确认或修订后，
   用 CLI `make-id --slug` 生成 ID 与规范化文件名，以相应模板在 `proposals/` 或
   `bugs/` 写入对象文件，初始状态为 `draft`。
7. 展示所有 draft、确认事实、排除范围和 Proposal 依赖后结束本 intent。用户在后续
   显式调用 `$mdf doc review`，并在 `draft` 状态通过 `targeted validation` 后，才可
   确认转为 `ready`；普通对象不在此流程关闭，也不填 `fulfilled_in`/`fixed_in`。
