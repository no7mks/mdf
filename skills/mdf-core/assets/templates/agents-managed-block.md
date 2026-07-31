<!-- MDF:BEGIN -->
## Mars Docs Flow

- 本仓库使用 `.mdf/manifest.yaml` 描述 MDF schema、状态和事实基线。
- “当前”只指 checkout 的 Git revision；计划写入 Requirement/Bug/Change，已实现事实写入
  `docs/product/` 或 `docs/system/`。
- `CONTEXT.md` 只维护领域词典；重要且已决定的长期取舍写入 `docs/adr/`。
- 工作项状态只使用 `draft`、`ready`、`closed`；feature/bugfix 完成时不得提前关闭。
- 只有用户显式调用 `mdf-*` 入口时才执行对应工作流；不得隐式接单。`mdf-core` 不是用户入口。
- release/hotfix 前必须通过零 finding 的 MDF 全量审计。
- MDF 只维护本 marker 块；不要让 MDF 工作流覆盖本文件其他规则。
<!-- MDF:END -->
