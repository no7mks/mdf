# Review Doc

只在用户显式调用 `$mdf review-doc` 时执行。不要在普通需求讨论、Bug 排查或
编码任务中接管文档评审；不要自动 commit。

完整读取 `workflows/common.md`、`workflows/grill.md`、
`references/repository-contract.md`、`references/object-contract.md` 与
`references/workflows.md`。

1. 解析目标 Git 根 `REPO_ROOT` 后运行 `doctor`。只有 manifest 为 `ready`
   才继续；否则提示 `$mdf init-repo`。一次只评审一个 Requirement 或 Bug。
2. 新对象由用户指定 Requirement/Bug 类型与 slug，收敛后用 CLI `make-id`
   创建 draft。修订既有对象时必须提供 canonical ID（`req-`/`bug-`）或仓库
   相对路径；缺失或歧义时一次只问一个消歧问题。closed 或 archive 对象拒绝修改。
3. 既有 ready 对象开始评审时立即转为 draft。取消、暂停或未确认最终内容时保持
   draft；用户可 commit 后在后续调用继续。
4. 使用内部 grill 工作流一次只澄清一个影响成稿的事实或取舍，并先查仓库证据。
   Requirement 收敛 Problem、Desired Outcome、Scope 和可验证 Acceptance
   Criteria；Bug 收敛 Observed/Expected Behavior、Reproduction、Impact、
   Regression Evidence Required、`found_in` 与 active severity。
5. 展示完整 draft、确认事实、排除范围及既有对象 diff。只有用户明确确认才转
   ready；之后运行 targeted validation。失败时保留 draft 和现场；普通对象不在
   此流程关闭，也不填 `fulfilled_in`/`fixed_in`。
