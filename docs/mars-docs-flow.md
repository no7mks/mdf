# Mars Docs Flow（MDF）V2

MDF 是一组本地优先 Agent 文档 Skill。用户显式调用五个业务入口；`mdf-core` 是内部被动组件。`mdf-init-repo` 与
`mdf-review-doc` 在需要逐题澄清时使用 `mdf-grill`。所有组件作为一套 V2 发布：`protocol_version`、
`tool_version` 与 `schema_version` 均为数字 `2`，不兼容 V1 schema、参数或 Skill 名称。

## 信息分层

| 类型 | 载体 |
|---|---|
| 当前事实 | `docs/product/`、`docs/system/`、配置、schema、测试 |
| 意图与工作 | Requirement、Bug、unreleased Change |
| 决策 | `docs/adr/` |
| 证据 | 测试、契约、生成物、配置和命令 |
| Agent 控制面 | `AGENTS.md`、`.mdf/manifest.yaml` |

Requirement/Bug 是计划与偏差，完成后不会自动变成当前事实。当前事实必须可由证据验证，且不得混写未来计划。

## 入口与审计

每个 outer workflow 从 clean worktree 开始；入口可产生改动，但绝不自动 commit，用户须自行复查并提交后再开始下一轮。

`$mdf-audit` 在 ready 的 Gitflow 分支上自动选择：

- `release/*` 执行 **release audit**：全量核对 `CONTEXT.md`、产品/系统事实页、ADR 与本次 Change 引用的
   Requirement/Bug。
- `feature/*`、`bugfix/*`、`hotfix/*` 执行 **change audit**：feature/bugfix 使用
  `develop...HEAD`，hotfix 使用 `master...HEAD`，检查变更及受影响事实。

两种审计都必须从 clean 基线开始，输出审计类型、Git 范围、覆盖内容、未触及理由和 finding 的结构化摘要。任何未初始化、非 ready、缺失基线
或 finding 都停止。release/hotfix 的零 finding 结论会压缩为非空 summary 写入版本根 CHANGE。

## 初始化与对象评审

`$mdf-init-repo` 将任何既有仓库接入 V2；旧 MDF/V1 仅是可参考材料。canonical 路径存在不兼容内容时，先展示包含受影响路径、保
留内容、拟补字段、基线和验证命令的完整迁移方案，取得一次明确确认后才原地迁移。

`$mdf-review-doc` 可新建或修订一个 active Requirement/Bug。修订目标必须是 canonical ID 或路径；ready
 对象开始评审即转 draft，未确认时保留 draft，确认后才验证并恢复 ready。它与 init 一样在需要逐题澄清时调用 `$mdf-grill`；
finish 不使用 mdf-grill。

## 目录与版本记录

```text
changes/
├── unreleased/<feature-or-bugfix-slug>/CHANGE.md
└── <version>/
    ├── CHANGE.md
    └── <feature-or-bugfix-slug>/CHANGE.md   # release 才有 child
```

feature/bugfix finish 先完成 change audit 与 clean-gated Core 步骤，再写入事实修复、复核最终内容、定向验证
并生成 child Change。release/hotfix 在审计发现需要修复时写入后停止；用户提交后重跑。零 finding 时调用 closeout，传
入：

```bash
python skills/mdf-core/scripts/mdf.py release-closeout \
  --repo /path/to/project --release-date 2026-07-30 \
  --semantic-attestation-json \
  '{"semantic":"passed","finding_count":0,"summary":"release audit: zero findings"}'
```

semantic attestation 在 preview/apply 都必填，`summary` 非空，且禁止 `waivers`。Core 信任
Agent 的语义判断，但会将简短摘要记录在版本根 CHANGE。apply 才执行 `verification.commands`；命令成功后
worktree 必须仍 clean，随后直接写入并 full validate。

## Bug 规则

active Bug 必须有 `severity: critical|major|trivial` 和 `found_in`。未发布线使用裸值
`found_in: unreleased`，不是伪 SemVer。Change 的 Bug outcome 是 `fixed`、`closed`、
`deferred`，每个 Bug 只能出现一次。

| outcome | closeout 结果 |
|---|---|
| fixed | `status: closed`、`resolution: fixed`、`fixed_in: <version>` |
| closed | 非 fixed 终态，无 fixed-in |
| deferred | 保持 ready、无 resolution/fixed-in、不归档 |

critical 只能 fixed；major deferred/wont-fix 需要用户明确接受、理由和 follow-up；每个 `ready` +
`found_in: unreleased` Bug 都必须分类。duplicate 只用 `duplicate_of` 指向 canonical Bug，不进
入 outcome，并与 canonical 一起归档。
