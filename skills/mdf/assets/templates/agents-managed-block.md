<!-- MDF:BEGIN -->

## Mars Development Flow

- 你的角色是维护者，按需读取以下入口：
  - [README.md](README.md)：项目定位。
  - [PROJECT.md](PROJECT.md)：维护工作的起点；遵循其中的验证要求。
  - [GLOSSARY.md](GLOSSARY.md)：领域术语。
  - [docs/system/overview.md](docs/system/overview.md)：系统边界。
  - [docs/README.md](docs/README.md)：按主题定位，只打开本次相关的一两份页面。
- 当前行为以事实页为准；修改行为或发现冲突时核对源码。
  - 事实页记录当前检出版本；一条契约只住一页。
  - 架构问题读架构主题；对外可观察行为变化时同步用户指南。
  - 点名具体 ID 或事实页链接到工作上下文、ADR、Proposal、Bug 时再读取；ADR 记录理由。
  - CodeWiki 用于按需搜索符号，由 CodeWiki 管理。
- 执行的每条命令都要留下完整日志或报告。
  - 优先读工具或系统自己写的日志与报告，不另 tee。
  - `$mdf` / `mdf.py`、pytest/JUnit 与带 `--log` 的工具读其产物。
  - 其他命令用 `mdf.py run --repo <根> -- <命令>`，不要 tee。
  - Core 不可用时才 tee 进 `.mdf/logs/<时间戳>-<名称>.log`，并去掉终端控制符。
  - 用 grep、head、tail 等截断时先完整落盘再截取，并以 `pipefail` 保留原命令退出码。
  - 失败时先读已有产物，不为查看输出而重跑。
- 沟通 Bug、Proposal、Jot、ADR 时写完整 ID（`bug-` / `prp-` / `jot-` /
  `adr-` 前缀），不得省略前缀或只写序号/短码/slug。
- 仅在用户显式调用 `$mdf …` 时执行对应 MDF 流程，不自动触发其他用户入口。

<!-- MDF:END -->
