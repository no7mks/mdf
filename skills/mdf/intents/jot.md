# Jot

不要自动 commit。

完整读取 `intents/common.md`、`intents/grill.md`、
`references/repository-contract.md` 与 `references/object-contract.md`。

`$mdf jot` 追加一条 Jot；`$mdf jot promote` 提升一条既有 Jot。不要接受其他子动作。

## 1. 入口检查

1. 解析目标 Git 根 `REPO_ROOT` 后运行 `doctor`。只有
   `normal_workflows_allowed` 为 `true` 才继续；`manifest` 未就绪时提示
   `$mdf init`，其他 findings 则报告并停止。
2. 同一次调用只处理一个 Jot。保留 Jot 原文；不得把它重写为当前事实、Proposal、
   Bug 或任务。

## 2. 记录

仅在用户调用 `$mdf jot` 时执行。

1. 要求用户提供要记录的内容；缺失时一次只问一个问题。内容可以是想法、优化、
   小问题、观察或其他未定性信息，不要求先判断类型、优先级或可行性。
2. 调用 `make-jot-id` 生成 ID。为该条目生成简短标题，但正文必须保留用户输入的
   原始含义和细节。在 `JOTS.md` 末尾追加完整 marker 条目。
3. 运行 `targeted validation`。成功后展示新增条目与 diff，提醒用户自行复查并
   commit；失败时保留现场并报告 findings。

## 3. 提升

仅在用户调用 `$mdf jot promote` 时执行。

1. 用户必须提供一个 existing `jot-` ID。缺失或歧义时一次只问一个消歧问题；读取
   对应完整 marker 条目，并保留其正文作为成稿输入。
2. 使用内部 grill intent 一次只澄清一个影响成稿的事实或取舍，并先查仓库证据。
   收敛 Proposal 的 Problem、Desired Outcome、Scope 与可验证 Acceptance Criteria，
   或 Bug 的 Observed/Expected Behavior、Reproduction、Impact、Regression Evidence
   Required、`found_in` 与 active severity。
3. 展示完整 Proposal 或 Bug draft、确认事实与排除范围。只有用户明确确认才调用
   `make-id`、写入目标对象，并在 `draft` 状态运行 `targeted validation`。失败时保留
   draft 和原 Jot；不得删除原 Jot。
4. draft 校验通过后，将对象转为 `ready`，再从 `JOTS.md` 删除所选 marker 条目，
   并再次运行 `targeted validation`。任何失败都保留现场并报告 findings；绝不自动
   commit。成功时展示两个文件的完整 diff，提醒用户将“创建 Proposal/Bug 与移除
   Jot”提交为同一个独立 commit。
