<!-- MDF:BEGIN -->

## Mars Development Flow

- 你的角色是维护者，不是终端用户。不要从根 `README.md` 或 `docs/user-guide/`
  开始通读；维护工作先读 `PROJECT.md`（验证、技术栈、目录约定与文档入口）。
- 系统边界是 `docs/system/overview.md`。需要按主题找文档时打开 `docs/README.md`：
  只打开与本次相关的一份 `docs/system/` 主题叶，不通读
  `docs/system/` 或 `docs/user-guide/`。
- grep、CodeWiki 等搜索只用来定位路径；定位后只读命中的那一份或 `docs/README.md`
  指定的一两份，不把全部命中读进上下文。
- `README.md` 只用于项目定位，`GLOSSARY.md` 用于领域术语；不把根文档当作
  行为事实来源。最短可运行路径在 `docs/user-guide/`。
- 当前行为以 `docs/system/` 与 `docs/user-guide/` 的事实页为准；一条契约只住
  一页，其他页只链接。事实页已覆盖的行为不从源码重新推断，除非本次要修改该行为
  或发现文档与实现冲突。
- `docs/user-guide/` 面向使用者；维护改动默认不打开，改动对外可观察行为时
  必须打开并同步。架构问题以 `docs/system/architecture/` 为准。
- 默认不读取 `docs/context/`（含 ADR）、Proposal 与 Bug，除非本次点名具体 ID
  或事实页链接到它。ADR 只记录理由，不作为当前结构来源。
- `docs/repowiki/` 存在时由 CodeWiki 管理、用于按需搜索符号，不得人工修改；
  不存在时忽略。
- `docs/system/`、`docs/user-guide/` 只记录当前检出版本的事实，不混入待实现计划。
- 维护改动按 `PROJECT.md` 的验证要求执行检查。测试分类、失败语义与 skip 以
  `docs/system/testing/` 为准。
- 执行的每条命令都要留下完整日志或报告：Agent 直接运行的命令把 stdout 与 stderr
  tee 进 `.mdf/logs/<时间戳>-<名称>.log`；用 grep、head、tail 等截断时先完整落盘再截取，
  并以 `pipefail` 保留原命令退出码；失败时先读日志与报告，不为查看输出而重跑。
- 沟通 Bug、Proposal、Jot、ADR 时写完整 ID（`bug-` / `prp-` / `jot-` /
  `adr-` 前缀），不得省略前缀或只写序号/短码/slug。
- 仅在用户显式调用 `$mdf …` 时执行对应 MDF 流程，不自动触发其他用户入口。

<!-- MDF:END -->
