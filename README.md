# Mars Development Flow（MDF）

MDF 是一套本地优先的 Agent 文档流程。它使用版本化文件管理当前事实、工作
意图、重要决策、可执行证据和 Agent 控制面。

## 使用

MDF 只发布一个 Skill。安装后显式调用 `$mdf <command>`：

| 命令 | 用途 |
| --- | --- |
| `$mdf init` | 初始化或更新仓库的 MDF 文档系统 |
| `$mdf next [方向]` | 发现并确认下一步 MVP，产出有依赖顺序的 Proposal |
| `$mdf codewiki generate` | 用 CodeWiki MCP 新建仓库结构 Wiki |
| `$mdf codewiki update` | 增量更新符合 MDF 契约的结构 Wiki |
| `$mdf start` | 按 Gitflow 创建并推送交付分支 |
| `$mdf jot` | 追加一条未分诊的随手记录 |
| `$mdf jot promote` | 提升一条 Jot 为 Proposal 或 Bug 并移除原条目 |
| `$mdf intake` | 将外部想法或临时来源分诊为 Bug 和/或多个 Proposal |
| `$mdf bug create` | 按已确认的内容手动创建一个 open Bug |
| `$mdf prp create` | 按已确认的内容手动创建一个 draft Proposal |
| `$mdf prp review` | 修订单个 active Proposal，并通过验证后转为 ready |
| `$mdf archive` | 归档 closed Proposal 及 closed/rejected Bug |
| `$mdf finish` | 按 Gitflow 分支完成审计与收口 |
| `$mdf audit` | 审阅当前文档与实现的覆盖、证据和语义是否相符 |
| `$mdf clarify <议题>` | 逐题压力测试计划、决策或想法 |

裸 `$mdf` 只显示帮助。所有意图都必须显式调用，入口可写入但不自动提交工作区改动；
用户须复查并提交，下一次调用从 clean worktree 开始。仅 `finish-gitflow`
会创建流程规定的 merge commit。

供 MDF 维护者查阅的[确定性 CLI 参考](./docs/product/reference/mdf-cli.md)
记录 `mdf.py` 的完整命令表、参数与实际副作用。该文档仅留在本仓库，
不会随 Skill 安装。

MDF 仅实现当前契约：不识别、维护或兼容历史 Skill、目录或调用形式。协议、工具与
schema 版本均为数字 `2`。

## 信息分层

| 类型 | 载体 |
| --- | --- |
| 当前事实 | `docs/product/`、`docs/system/`、配置、schema、测试 |
| 工作上下文 | `context/research/` |
| 代码结构 Wiki | `docs/repowiki/`；仅由 CodeWiki MCP 生成与更新 |
| 未分诊记录 | `JOTS.md` |
| 意图与工作 | Proposal、Bug、unreleased Change |
| 决策 | `docs/adr/` |
| 证据 | 测试、契约、生成物、配置和命令 |
| 项目维护 | `PROJECT.md` |
| Agent 指令 | `AGENTS.md`、`.mdf/manifest.yaml` |
| 领域术语 | `GLOSSARY.md` |

Proposal/Bug 是计划与偏差，完成后不会自动成为当前事实。当前事实必须可由证据
验证，且不得混写未来计划。

`JOTS.md` 是可随手追加的原始记录本；它不替代 Proposal、Bug 或任务管理。当一条
Jot 被提升为 Proposal 或 Bug 后，原条目会在同一份待提交改动中移除。

具体 intent、对象约束和仓库契约随唯一 Skill 一同安装，位于其内部的
`intents/`、`references/`、`assets/` 与 `scripts/`。

## 安装

请从 MDF 仓库获取完整技能集。先在目标仓库创建 Agent 的 Skills 目录，例如
`.codex/skills`，确认 MDF 源仓库工作区干净后安装：

```bash
mkdir -p /absolute/path/to/target-repository/.codex/skills
./mdf-deploy.sh install --target /absolute/path/to/target-repository
```

`install` 只从当前 `HEAD` 安装，并在 `mdf/references/.version` 写入完整 commit hash。
目标已有 `mdf` 时终止；升级时先运行 `unistall`，再运行 `install`。`diff` 分别显示
本地与目标相对该基线的改动。脚本不会修改目标仓库的 `.mdf/`、`docs/` 或业务文件。

## 维护

维护环境、验证命令与仓库约束见 [`PROJECT.md`](PROJECT.md)；测试范围和说明见
[tests/README.md](./tests/README.md)。
