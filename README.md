# Mars Docs Flow（MDF）

MDF 是一组本地优先的 Agent 文档 Skill。它使用版本化文件管理当前事实、工作意图、重要决策、可执行证据和 Agent 控制面。

## 技能集

| 组件             | 用途                                     |
| ---------------- | ---------------------------------------- |
| `mdf-core`       | 共享协议、模板与确定性 CLI；不是业务入口 |
| `mdf-init-repo`  | 初始化或更新仓库的 MDF 文档系统          |
| `mdf-review-doc` | 新建或修订单个 active Requirement / Bug  |
| `mdf-finish`     | 按 Gitflow 分支完成审计与收口            |
| `mdf-audit`      | 执行 change audit 或 release audit       |
| `mdf-archive`    | 归档已关闭工作项并重写链接               |
| `mdf-grill`      | 逐题压力测试计划、决策或想法             |

所有组件作为一套发布：`protocol_version`、`tool_version` 与 `schema_version`
均为数字 `2`。

用户显式调用五个业务入口：`mdf-init-repo`、`mdf-review-doc`、`mdf-finish`、
`mdf-audit` 与 `mdf-archive`。`mdf-core` 是内部被动组件； `mdf-init-repo` 与
`mdf-review-doc` 在需要逐题澄清时使用 `mdf-grill`。

## 协议与工作流

### 信息分层

| 类型         | 载体                                                |
| ------------ | --------------------------------------------------- |
| 当前事实     | `docs/product/`、`docs/system/`、配置、schema、测试 |
| 意图与工作   | Requirement、Bug、unreleased Change                 |
| 决策         | `docs/adr/`                                         |
| 证据         | 测试、契约、生成物、配置和命令                      |
| Agent 控制面 | `AGENTS.md`、`.mdf/manifest.yaml`                   |

Requirement/Bug 是计划与偏差，完成后不会自动变成当前事实。当前事实必须可由证据验证，且不得混写未来计划。一个 Git 仓库对应一个 MDF
上下文与版本线；MDF 不管理 PR、RFC、外部 tracker、owner、priority、Task 或迭代。

### 入口与审计

每个 outer workflow 从 clean
worktree 开始；入口可产生改动，但绝不自动 commit，用户须自行复查并提交后再开始下一轮。

`$mdf-audit` 在 ready 的 Gitflow 分支上自动选择：

- `release/*` 执行 **release audit**：全量核对
  `CONTEXT.md`、产品/系统事实页、ADR 与本次 Change 引用的 Requirement/Bug。
- `feature/*`、`bugfix/*`、`hotfix/*` 执行 **change audit**：feature/bugfix 使用
  `develop...HEAD`，hotfix 使用 `master...HEAD`，检查变更及受影响事实。

两种审计都必须从 clean 基线开始，输出审计类型、Git 范围、覆盖内容、未触及理由和 finding 的结构化摘要。任何未初始化、非 ready、
缺失基线或 finding 都停止。release/hotfix 的零 finding 结论会压缩为非空 summary 写入版本根 CHANGE。

### 初始化与对象评审

`$mdf-init-repo`
为既有仓库初始化或更新 MDF 文档系统。canonical 路径已有内容时，先展示包含受影响路径、保留内容、拟补字段、基线和验证命令的完整写入方案，
取得一次明确确认后才写入。

`$mdf-review-doc` 可新建或修订一个 active
Requirement/Bug。修订目标必须是 canonical
ID 或路径；ready 对象开始评审即转 draft，未确认时保留 draft，确认后才验证并恢复 ready。它与 init 一样在需要逐题澄清时调用
`$mdf-grill`；finish 不使用 mdf-grill。

### 目录与版本记录

```text
changes/
├── unreleased/<feature-or-bugfix-slug>/CHANGE.md
└── <version>/
    ├── CHANGE.md
    └── <feature-or-bugfix-slug>/CHANGE.md   # release 才有 child
```

feature/bugfix finish 先完成 change audit 与 clean-gated
Core 步骤，再写入事实修复、复核最终内容、定向验证并生成 child
Change。release/hotfix 在审计发现需要修复时写入后停止；用户提交后重跑。零 finding 时调用 closeout，传入：

```bash
python skills/mdf-core/scripts/mdf.py release-closeout \
  --repo /path/to/project --release-date 2026-07-30 \
  --semantic-attestation-json \
  '{"semantic":"passed","finding_count":0,
  "summary":"release audit: zero findings"}'
```

semantic attestation 在 preview/apply 都必填，`summary` 非空，且禁止
`waivers`。Core 信任 Agent 的语义判断，但会将简短摘要记录在版本根 CHANGE。apply 才执行
`verification.commands`；命令成功后 worktree 必须仍 clean，随后直接写入并 full
validate。

`--release-date` 必须显式提供。hotfix 还必须显式提供严格的
`--hotfix-change-json`：body 非空，至少一条 evidence 和一条 release
note；`change_kind`、`source_branch`
由 Core 按当前分支注入。版本根 Change 将按 child
Change 顺序聚合 evidence，再追加 manifest 验证命令并按首次出现顺序去重。

### Bug 规则

active Bug 必须有 `severity: critical|major|trivial` 和
`found_in`。未发布线使用裸值
`found_in: unreleased`，不是伪 SemVer。Change 的 Bug outcome 是
`fixed`、`closed`、 `deferred`，每个 Bug 只能出现一次。

| outcome  | closeout 结果                                                |
| -------- | ------------------------------------------------------------ |
| fixed    | `status: closed`、`resolution: fixed`、`fixed_in: <version>` |
| closed   | 非 fixed 终态，无 fixed-in                                   |
| deferred | 保持 ready、无 resolution/fixed-in、不归档                   |

critical 只能 fixed；major
deferred/wont-fix 需要用户明确接受、理由和 follow-up；每个 `ready` +
`found_in: unreleased` Bug 都必须分类。duplicate 只用 `duplicate_of`
指向 canonical Bug，不进入 outcome。closed
duplicate 可以在 canonical 仍 ready 时存在；手动 archive 会拒绝该状态，release
closeout 关闭 canonical 后将整个 group 一起归档。

## 安装

请前往 [MDF 独立仓库](http://10.1.5.65:8929/mars/mdf)
获取并安装完整技能集。克隆仓库后，可用根目录的 `link_skills.sh`
将所有技能软链到目标项目或用户级 Agent skills 目录：

```bash
./link_skills.sh --project /absolute/path/to/target-repository
./link_skills.sh codex --global
```

每次安装或升级都会先卸载目标 Agent skills 目录中的全部 `mdf-*`
Skill，再安装当前技能集；不会修改目标仓库的 `.mdf/` 或 `docs/` 产出物。

按需安装某个入口时，必须同时安装同套 `mdf-core`； `mdf-init-repo` 和
`mdf-review-doc` 还必须同时安装 `mdf-grill`。

## 测试

MDF 测试只依赖 Python 标准库、Git 和 pytest：

```bash
python -m pip install -r tests/requirements-test.txt
python -m pytest
```

测试范围和说明见 [tests/README.md](./tests/README.md)。
