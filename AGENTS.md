# AGENTS.md

本文件仅面向在本仓库中工作的 Agent。维护工作所需的项目资料见
[`PROJECT.md`](PROJECT.md)。

## Agent 行为

- 开始工作前读取 `README.md`；维护工作再读取 `PROJECT.md`，遇到领域术语时查阅
  `GLOSSARY.md`。
- 按 `PROJECT.md` 中的验证要求执行检查。
- 执行的每条命令都要留下完整日志或报告：测试读 `.test-reports/` 的 JUnit 报告，其他命令
  把 stdout 与 stderr tee 进 `.test-reports/<时间戳>-<名称>.log`；失败时先读日志与报告，
  不为查看输出而重跑。
- 遵守当前 MDF 契约，不得引入旧版兼容、迁移、识别或运行时分支。
- 本仓库自身只使用 `master` 一个 Git 分支：直接在 `master` 上开发与提交，
  不创建 `develop`、feature/bugfix/release/hotfix 或其他交付分支，也不对本仓
  执行 `$mdf start` / `$mdf finish` 的 Gitflow。
- 未经用户明确要求，不得删除目标仓库的 `.mdf/` 或 `docs/` 产出物。
