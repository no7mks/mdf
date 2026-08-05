# MDF 公共规则

需要确定性操作时使用 `python3 "$MDF_ROOT/scripts/mdf.py"`；CLI 只做确定性工作，
工作流负责语义判断。

按操作需要读取：

- `references/repository-contract.md`：仓库目录、`manifest` 与`基线`规则；
- `references/object-contract.md`：Proposal、Bug 与 Change 的 schema 和不变量。

## Clean worktree

- 仅在外层工作流入口检查一次 clean worktree。
- 按 Git 语义判断 clean：被 `.gitignore` 忽略的文件不构成 dirty worktree。
- Skill 运行写入 `.lark/` 的令牌文件属于上述允许情况。
- 同一次工作流的写入会使工作区变 dirty；用户针对中间产物提出反馈时，
  必须继续该工作流，不得重复 clean 检查而拒绝修改。

## 写入后的工作区

- 入口可产生改动，但绝不自动 commit。
- 用户须自行复查并提交；下一次独立 MDF 调用从 clean worktree 开始。
