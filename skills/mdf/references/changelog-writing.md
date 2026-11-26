# CHANGELOG 编写规范

本文定义 child `CHANGE.md` 的 `release_notes` 与根 `CHANGELOG.md` 的编写、筛选与润色规则，
使发布说明与 annotated tag 正文面向读者清晰可读。

## 职责边界

本节区分机器审计记录与面向人的发布说明，避免把内部 YAML 数组机械透传给读者。

| 载体 | 主要读者与用途 | 一致性要求 |
| --- | --- | --- |
| `changes/<version>/CHANGE.md` 与 child `CHANGE.md` | 机器审计、对象追溯与 SemVer bump 校验 | 完整保留 outcomes、evidence 与 `release_notes` 分类 |
| 根 `CHANGELOG.md`（与 `publish` tag 正文） | 研发、测试、运维与产品读者 | 覆盖全部应发布事实与已核实 PR/MR 链接，不要求与 YAML 字符串逐字相同 |

## 准入与过滤

本节规定哪些变更进入根 `CHANGELOG.md`，哪些应写 `release_notes: none`。

| 变更性质 | 处置 |
| --- | --- |
| 业务、用户或外部调用方可感知的变化（功能、接口、计费、修复、安全） | 进入根 `CHANGELOG.md` |
| 线上运维、部署工具、运行配置键增删、兼容约束与一次性线上补偿工具 | 进入根 `CHANGELOG.md`，加 `[运维]` 标识 |
| 未实施提案或设计文档保全、纯文档整理、MDF 自身升级 | 写 `release_notes: none`，不进根 `CHANGELOG.md` |
| 纯测试分层与预算调整、测试 fixture 或用例修补、临时锁定失败用例 | 写 `release_notes: none`，不进根 `CHANGELOG.md` |
| 纯 CI 内部编排路由与内部开发成员名单微调 | 写 `release_notes: none`，不进根 `CHANGELOG.md` |

- 过滤项仍完整保留在 `changes/<version>/` 与 `release-reconciliation.md` 中供审计追溯。
- 若整版不含业务或运维变化、确需发布且将触发 `empty_release_notes`，在首次 `consolidate` 聚合前写入来源对象：
  - release 写入最具代表性的真实 child `CHANGE.md`（不伪造空壳 child），hotfix 写入 `--hotfix-change-json`。
  - minor / major 版本用 `Changed` 概括本版工程或维护范围。
  - patch 版本按 SemVer 只允许 `Fixed` 或 `Security`；若整版不含任何修复或安全变更，应改为 minor 或取消发版，不得把非修复项硬标为 `Fixed`。

## 结构与排序

本节固定根 `CHANGELOG.md` 版本章节的 Markdown 结构与条目顺序。

- 严格只使用 Keep a Changelog 的六个标准英文子标题：`Added`、`Changed`、`Deprecated`、`Removed`、`Fixed`、`Security`。
  - 不增设版本概要段、独立升级小节或工程维护等自定义子标题。
- 按变更实际性质归类，避免默认全填 `Changed`：
  - `Added`：新增接口、命令、功能、容灾或补偿能力。
  - `Changed`：既有行为、模型、参数策略或交互调整。
  - `Deprecated` / `Removed`：弃用或移除接口、命令与配置键（`Removed` 须伴随 `breaking: true`）。
  - `Fixed`：缺陷与线上异常修复。
  - `Security`：鉴权边界、凭据或安全加固。
- 同一分类内按「升级或兼容敏感项 → 业务核心变更 → `[运维]` 部署与运维变更」排序，禁止按 child slug 字母序或提交时间直出。
- 一条只说明一件事；同一能力含 3 项以上子点时用二级列表展开，避免用多个分号拼成超长句。
- 已核实的 PR/MR 链接（`[pr#123](<url>)` / `[mr!123](<url>)`）保留在对应主条目末尾。

## 表达与升级注意

本节规定条目措辞、代码格式与高危影响的提炼方式。

- 每条以 `**主题**：` 开头，先写对象与可观察结果或业务影响，再补必要条件与背景；运维项写作 `**[运维] 主题**：`。
- 禁止直接抛出未解释的内部错误码、状态机或存储术语；出现时必须说明对外表现与影响。
- 配置键、命令行参数、环境变量、API 路径、HTTP Header、文件名与版本号一律用反引号包裹。
- 必须通读本版全部 child `CHANGE.md` 与版本根 `CHANGE.md` 的「结果」与「已知偏差」，提炼配置删键、Header 强制校验、命令替换、回滚前置与迁移要求：
  - 将相关条目置顶排在所属分类最前。
  - 在该条目下用二级列表补充升级提醒，以行首提醒标记写出「升级注意」、具体影响与前置动作：
  - ⚠️ **升级注意**：示例写法——开启某开关后未带指定 Header 将返回 `426`，调用方须先补齐。

## 跨线去重与定稿时机

本节规定 support hotfix 跨线条目处理与 `CHANGELOG.md` 的最终润色时机。

- 已在 `support/*` hotfix 发布的修复后续合入主线发 minor release 时，若 `CHANGELOG.md` 已有该 patch 章节，不重复照抄同一条目；确需提及则在条目中注明「同步自 `v<patch>`」。
- release 在首次 `consolidate` CLI 聚合后，须按本规范润色本版 `CHANGELOG.md` 章节，提交后执行 `consolidate --incremental` 锁定。
- hotfix 在构造 `--hotfix-change-json` 时即按本规范编写 `release_notes`；必要时在首次生成后润色 `CHANGELOG.md` 并执行 `consolidate --incremental`。
