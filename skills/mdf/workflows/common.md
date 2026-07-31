# MDF 公共规则

所有命令都由 `$mdf <command>` 显式触发。需要确定性操作时使用
`python3 "$MDF_ROOT/scripts/mdf.py"`；CLI 只做确定性工作，工作流负责语义判断。

按操作需要读取：

- `references/repository-contract.md`：仓库目录、manifest 与基线规则；
- `references/object-contract.md`：Requirement、Bug、Change 与 closeout 规则；
- `references/workflows.md`：各命令的跨流程约束。

任何写入前都要求 clean worktree。入口可产生改动但绝不自动 commit；用户须自行
复查并提交，下一次 MDF 调用从 clean worktree 开始。
