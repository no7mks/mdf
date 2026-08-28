# MDF 公共意图规则

## 工作流（唯一执行契约）

1. **约束**；需要确定性操作时使用
   `python3 "$MDF_ROOT/scripts/mdf.py"`，语义判断留给 intent；证据：CLI 调用与
   intent 判断各自可追溯；通过 → 按适用规则继续；失败 → 停止，不得用 CLI 模拟语义判断。
2. **约束**；仅在外层 intent 入口检查一次 clean worktree，并按 Git 语义判断；
   `.gitignore` 忽略文件和 Skill 写入的 `.lark/` 令牌不构成 dirty；
   证据：入口检查记录；通过 → 执行对应 intent；失败 → 停止。
3. **约束**；仅当同次 intent 已写入工作区时，接受用户对中间产物的反馈；不得重复
   clean 检查而拒绝修改；证据：同次调用上下文；通过 → 继续修改；失败 → 报告边界不明。
4. **约束**；写入失败时保留现场并报告 findings；证据：失败现场与报告；
   通过 → 等待用户处理；失败 → 停止。
5. **约束**；仅当 intent 产生待提交工作区改动时，要求用户复查并自行提交；绝不自动
   commit；证据：用户复查与提交；通过 → 下一次独立调用；失败 → 停止。

## 术语与数据结构

按操作需要读取：`references/repository-contract.md` 定义仓库目录、`manifest` 与
`基线`；`references/object-contract.md` 定义 Proposal、Bug 与 Change 的 schema
和不变量。
