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
    `$mdf bug create`、`$mdf prp create` 与 `$mdf prp review`；不得隐式接单；交付阶段可按确认范围提交。
    交付阶段与 `finish-gitflow` 按流程执行必要的 no-ff 合并。
  - Proposal 状态为 draft、ready、implemented、released、rejected、replaced。
    Bug 状态为 open、fixed、closed、rejected，保持其二次验证与发布约束。
  - release 收口前必须通过 MDF 全量审计；hotfix 收口前通过交付范围审计；两者均须零问题项。

- 托管边界
  - MDF 只管理本标记区块，不得覆盖 `AGENTS.md` 的其他规则。

- feature 交付：start → design → [write-tests ∥ implement] → converge → review → finish。
- 当前事实使用 `$mdf fact update` 与 `$mdf fact audit`；finish 前段内部同步事实。
- `$mdf next` 只读展示 ready 依赖；`$mdf prp split` 拆分未开工对象。

<!-- MDF:END -->
