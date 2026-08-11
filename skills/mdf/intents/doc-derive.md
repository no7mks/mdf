# Doc Derive

不要自动 commit，也不创建 Proposal 或 Bug。

完整读取 `intents/common.md`、`intents/grill.md`、
`references/repository-contract.md` 与 `references/object-contract.md`。

1. 解析目标 Git 根 `REPO_ROOT` 后运行 `doctor`。只有
   `normal_workflows_allowed` 为 `true` 才继续；`manifest` 未就绪时提示
   `$mdf init`，其他 findings 则报告并停止。
2. 用户指定 `context/requirements/` 中的一份需求来源；缺失或歧义时一次只问一个
   消歧问题。核对来源链接、版本或快照和采用范围；不把来源内容当作当前事实。
3. 在拆分任何 Proposal 前，通过内部 grill intent 一次只确认一个 MVP 要素：目标
   用户、端到端路径、最小用户价值、可验证信号和明确延期项。展示 MVP，只有用户
   明确确认后才继续。
4. 以已确认 MVP 为约束生成多个 Proposal 候选。优先形成支撑端到端价值的切片；只有
   MVP 不可缺少的技术使能才单列 Proposal。对每项列出中文标题、建议英文 slug、
   Problem、Desired Outcome、MVP 关系、依赖和首期或延期状态。
5. 展示候选清单和依赖图，逐项澄清影响拆分的事实或取舍。用户明确确认后，将 MVP、
   拆分依据、候选清单和依赖写入 `context/planning/`；不得写入 `proposals/`。
6. 提示用户对每项已确认候选显式调用 `$mdf doc create`。创建时重新确认标题与英文
   slug；不得批量创建或自动将候选项转为 `ready`。
