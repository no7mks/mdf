# MDF 内部设计说明（不发布）

本文仅供维护者理解设计取舍，不是已发布规范，也不定义运行时优先级。可执行契约以已发布的 README、Core
references 和入口 Skill 为准；`protocol_version`、`tool_version` 与
`schema_version` 均为数字 `2`。

## 产品边界

- 一个 Git 仓库对应一个 MDF 上下文和一条版本线。
- MDF 管理本地 Requirement、Bug、变更快照、当前产品/系统事实、ADR 与证据；不管理 PR、RFC、外部 tracker、owner、
  priority、Task 或迭代。
- `mdf-core` 是内部被动组件，绝不直接承接业务请求。`mdf-init-repo` 与
  `mdf-review-doc` 在需要逐题澄清时调用 `mdf-grill`。
- MDF 面向本机协作仓库；仓库内容及 manifest 中的验证命令受信任，但事实仍必须与代码、配置、schema、测试对齐。

## 分支与入口

Gitflow 语义为 `feature/*`、`bugfix/*`、`release/<semver>`、`hotfix/<semver>`。
`$mdf-finish` 与 `$mdf-audit`
都要求上述分支；init、review、archive 不新增分支硬门禁。

- `mdf-audit`：按分支执行 change audit 或 release audit；只读；依赖 `mdf-core`。
- `mdf-init-repo`：初始化或更新配置；写入；依赖 `mdf-core`、`mdf-grill`。
- `mdf-review-doc`：澄清单个 Requirement/Bug；写入；依赖 `mdf-core`、`mdf-grill`。
- `mdf-finish`：按 Gitflow 收口；写入；依赖 `mdf-core`、`mdf-audit`。
- `mdf-archive`：手动归档 closed 对象；写入；依赖 `mdf-core`。
- `mdf-grill`：逐题压力测试计划、决策或想法；只读；由 init/review 需要澄清时调用。

入口先验证 Core。`mdf-init-repo` 与 `mdf-review-doc`
在需要逐题澄清时解析并调用同级 `mdf-grill`；缺失时停止，不得替换成其他盘问流程。

## 信息与真相

1. **当前事实**：已实现的产品能力和系统结构，由产品/系统文档表达。
2. **意图与工作**：Requirement、Bug、未发布 Change。
3. **决策记录**：已作出的重要 ADR。
4. **可执行证据**：测试、契约、配置、schema、生成物和可重跑命令。
5. **Agent 控制面**：`.mdf/manifest.yaml` 与 `AGENTS.md` 的 MDF 托管块。

“当前”是当前 checkout 的 Git
revision，不是计划或生产环境。代码、配置、schema 与测试是最终技术证据；Diátaxis 页面必须描述真实行为。工作对象 ready
或代码完成都不能自动证明当前事实成立。

## 严格执行

- 初始化中 manifest 只能为 `initializing`；只有 `$mdf-init-repo`
  可继续。八项基线、当前事实与非空 `verification.commands` 完成后才能 `ready`。
- `verification.commands`
  是共享的受信任字符串列表。初始化时可以为空；ready、full
  validation 和 closeout 必须非空。调整它必须重新显式调用 `$mdf-init-repo`。
- 所有 MDF 入口在 outer workflow 开始前要求 clean
  worktree；所有 Core 写命令（init、move-change、archive、release-closeout）在 preview 和
apply 前仍要求 clean。入口不自动 commit。
- `--dry-run`
  只是按需预览，不产生确认、digest 或 apply 绑定。显式入口调用授权正常写入。Requirement/Bug 最终内容确认，以及 major
  Bug deferred/`wont-fix` 的接受、理由、follow-up 是唯一保留的用户决策门禁。
- Core 直接写入目标仓库；post-validation 失败时保留现场，由 Git 历史处理。
- closeout preview 需要 passed、零 finding、非空 summary 的 semantic
  attestation，但不执行验证命令，只输出版本、outcome、移动、受影响文件和配置命令摘要。apply 执行 manifest 命令，成功后
worktree 仍须 clean。

## 术语

- `$mdf-audit`：用户入口，执行 release 全审或其他 Gitflow 分支的变更审计。
- CLI `doctor`：Core 只读状态报告。
- CLI `validate`：Core 确定性校验，`operation` 恒为 `validate`。
- `verification.commands`：closeout apply 在目标仓库执行的共享验证命令。
- Change「Audit」段：版本根 Change 的确定性、命令与语义 attestation 记录。
