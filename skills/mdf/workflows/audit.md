# Audit

可由同一次 `$mdf init`、`$mdf finish` 内部委托。它只读，不写入、移动、提交或
生成持久报告。

完整读取 `workflows/common.md` 与 `references/repository-contract.md`。

## 审阅类型

- `全量审阅`：从文档和实现两个方向覆盖全部`当前事实文档`与全部产品、系统实现面。
  任何未触及的目录或生成物都要说明不相关的理由。
- `范围审阅`：从文档和实现两个方向覆盖调用方给定的实现与文档范围。调用方必须同时
  给出两类范围；即使未发现受影响的`当前事实文档`，也必须从实现侧审阅，并明确报告
  没有对应文档的行为或架构。

## 调用与状态

- 用户直接调用 `$mdf audit` 时，执行`全量审阅`。要求 `manifest` 为 `ready`，并在
  外层工作流入口检查 clean worktree。
- `$mdf init` 内部委托时，执行`全量审阅`。允许 `manifest` 为 `initializing`，且
  不得重复检查 clean worktree。
- `$mdf finish` 内部委托时，release 执行`全量审阅`；feature、bugfix、hotfix 执行
  `范围审阅`。后者的范围是`交付前检查`识别出的实现变更和受影响文档，不得重复
  检查 clean worktree。

## 审阅步骤

1. 从文档到实现：对范围内每份`当前事实文档`执行`事实复核`，检查陈述是否匹配
   当前 checkout 的代码、配置、schema、测试或生成物，且每项陈述都有有效
   `evidence`。
2. 从实现到文档：检查范围内的产品行为、系统边界、架构组件、接口、数据与运维
   实现是否已有`当前事实文档`。报告未记录的实现、过时或错误陈述、无法验证的
   `evidence`，以及把计划、候选或调研结论写成当前事实的内容。
3. 运行 `full validation`。`$mdf init` 的内部委托只允许
   `manifest.initializing` finding；其他 finding 一律报告。
4. 返回会话内结构化摘要：审阅类型、实现范围、文档范围、已复核文档、语义
   findings、`validation` findings 与未触及理由。

`audit` 不检查 Gitflow 分支、变更 diff、Proposal、Bug、Change、release 输入、
closeout 或 merge 条件；这些属于 `$mdf finish` 的`交付前检查`。
