<!-- MDF:BEGIN -->

## Mars Development Flow

- 开始工作前把 `docs/README.md` 当任务地图：只打开与本次任务相关的当前事实页，
  不通读 `docs/product/` 或 `docs/system/`。
- 按需读取根文档：`README.md` 用于项目定位与最短运行路径，`PROJECT.md` 用于
  验证命令与目录例外，`GLOSSARY.md` 用于领域术语；不把它们当作行为事实来源。
- 当前行为以 `docs/product/` 与 `docs/system/` 的事实页为准；事实页已覆盖的
  行为不从源码重新推断，除非本次要修改该行为或发现文档与实现冲突。
- 默认不读取 ADR、Proposal、Bug 与 `docs/context/`，除非任务点名具体 ID 或
  涉及长期取舍。
- `docs/repowiki/` 存在时由 CodeWiki 管理、用于定位符号，不得人工修改；
  不存在时忽略。
- `docs/product/`、`docs/system/` 只记录当前检出版本的事实，不混入待实现计划。
- 维护改动按 `PROJECT.md` 的验证要求执行检查。
- 沟通 Bug、Proposal、Jot、ADR 时写完整 ID（`bug-` / `prp-` / `jot-` /
  `adr-` 前缀），不得省略前缀或只写序号/短码/slug。
- 仅在用户显式调用 `$mdf …` 时执行对应 MDF 流程，不自动触发其他用户入口。

<!-- MDF:END -->
