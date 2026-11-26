# Check

`$mdf check [<path>...] [--scope full|branch|paths]` 运行只读静态检查。默认使用 `dev` 和 `branch`。

树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve scope | 约束 | 解析 Git 根与检查范围 | scope、路径 | 2 | 范围冲突则询问 |
| 2 | Check | 脚本 | 运行 check dev，报告 findings | JSON、退出码 | 结束 | 报告错误后结束 |

- 显式路径选 `paths`；路径与 `full` 或 `branch` 同用时询问。
- 仓内 Markdown 传 `--document-path`；module sourceset 内已跟踪实现文件传 `--implementation-path`。
- `docs/JOTS.md`、仓库外路径与两类均不匹配的路径须澄清。
- 运行 `check --repo "$REPO_ROOT" --profile dev`，附上上一步的范围参数。
- 报告 scope、实际执行与跳过的检查，以及 blocking 和 advisory findings。

| Profile | 调用场景 | 范围 |
| --- | --- | --- |
| `entry` | intent 检查控制面与 `normal_workflows_allowed` | 无 scope，可检查未初始化目录 |
| `objects` | 写对象后校验全局对象规则 | 默认 full，paths 附加被写入 PRP/Bug 的结构检查 |
| `dev` | 开发时校验契约、链接与文档 | 默认 branch，可选 full 或 paths |
| `closeout` | 收口或写后复验；对影响集检查 Git freshness | 默认 branch，可选 full 或 paths |

静态检查直接读取工作区。运行期间保持工作区稳定。需要不可变输入时，使用 [Fact Audit](fact-audit.md)。
