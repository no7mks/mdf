<!-- MDF:BEGIN -->

## Mars Development Flow

- 阅读与信息分层
  - 开始工作时先读取 `README.md`；维护工作再读取 `PROJECT.md`；遇到领域术语时
    查阅 `GLOSSARY.md`。
  - 当前事实只描述当前检出版本，写入 `docs/product/` 或 `docs/system/`。
  - `docs/repowiki/` 是 CodeWiki 受管生成物；不要人工直接修改其中内容。
  - 待实现意图写入 Proposal；已观察到的偏差写入 Bug。
  - Change 记录交付单元的结果、关联对象和证据；它不替代当前事实文档。
  - 未定性的随手记录写入 `JOTS.md`；它们不是 Proposal、Bug 或 Change。
  - `GLOSSARY.md` 只维护领域词典；重要且已决定的长期取舍写入 `docs/adr/`。

- 意图与状态
  - 仅在用户显式调用 `$mdf …` 时执行 MDF 意图命令，包括 `$mdf intake`、
    `$mdf bug create`、`$mdf prp create` 与 `$mdf prp review`；不得隐式接单或自动提交。
  - Proposal 状态只使用 `draft`、`ready`、`closed`；Bug 状态只使用 `open`、`fixed`、
    `closed`、`rejected`；feature/bugfix 不得提前关闭。
  - release/hotfix 收口前必须通过零问题项的 MDF 全量审计。

- 托管边界
  - MDF 只管理本标记区块，不得覆盖 `AGENTS.md` 的其他规则。
<!-- MDF:END -->
