# Mars Development Flow（MDF）

MDF 是一套本地优先的 Agent 文档流程。它使用版本化文件管理当前事实、工作
意图、重要决策、可执行证据和 Agent 控制面。

### Jev 可选加速

宿主可配置 Jev MCP；**无 Jev 时流程完全可用**，定型判断改由主 Agent（可能更慢）。
Agent 仅在写死步骤使用 `choice` / `noul` / `score` / `run`。

以 Cursor + OpenRouter + [`jev-cli`](https://pypi.org/project/jev-cli/) 为例
（CLI 与 MCP 共用 `jev auth` 凭证，不进目标仓）：

1. `uv tool install jev-cli`（得到 `jev` / `jev-mcp`）。
2. 写入 OpenRouter 密钥（隐藏输入，落盘
   `~/.config/jev-cli/credentials.json`，权限 `600`）：

```bash
jev auth set --provider openrouter
jev auth test --provider openrouter
```

3. 在 `~/.cursor/mcp.json` 增加 stdio 服务（只需 provider，不必 `envFile`）：

```json
{
  "mcpServers": {
    "jev": {
      "command": "jev-mcp",
      "env": { "JEV_PROVIDER": "openrouter" }
    }
  }
}
```

4. 重载 MCP；会话出现 `noul` / `choice` / `score` / `run` 后即可加速。
5. 换 key：再跑 `jev auth set --provider openrouter`。
   - 若环境里仍有 `OPENROUTER_API_KEY`，会盖过 credentials；换方案后新开终端
     / 重启 Cursor 再验。
   - 其他 provider：改 `JEV_PROVIDER`，并用对应
     `jev auth set --provider <名>`。

## 使用

MDF 只发布一个 Skill。安装后显式调用 `$mdf <command>`：

| 命令 | 用途 |
| --- | --- |
| `$mdf help` | 展示分组意图目录与调用示例 |
| `$mdf help <intent>` | 展示该 intent 的用法要点 |
| `$mdf bootstrap` | 为全新或几乎全新的项目建立 MDF 起点 |
| `$mdf init` | 接入已有项目或调整 MDF 配置；新项目转入 bootstrap，已有项目转入 migrate |
| `$mdf init migrate` | 将已有项目材料与布局收敛到当前 MDF 结构；也可 `$mdf migrate` |
| `$mdf tree [--depth N]` | 按 milestone 分组画出 draft/ready PRP 依赖树；也可 `$mdf prp tree` 或 `$mdf next?` |
| `$mdf next [--depth N]` | 续办在途或提示下一步；feature 上走交付；无在途时委托 tree |
| `$mdf codewiki generate` | 用 CodeWiki MCP 新建仓库结构 Wiki |
| `$mdf codewiki update` | 增量更新符合 MDF 契约的结构 Wiki |
| `$mdf deliver [<target>] [--auto-pilot] [--yolo]` | 持续推进到 close-out；可并行分派 subagent |
| `$mdf start` | 按 Gitflow 创建本地交付分支与 `<repo-name>-worktrees/` worktree |
| `$mdf jot` | 追加一条未分诊的随手记录 |
| `$mdf jot promote` | 提升一条 Jot 为 Proposal 或 Bug 并移除原条目 |
| `$mdf intake` | 将外部想法或临时来源分诊为 Bug 和/或多个 Proposal |
| `$mdf bug create` | 按已确认的内容手动创建一个 open Bug |
| `$mdf prp create` | 按已确认的内容手动创建一个 draft Proposal |
| `$mdf prp review` | 修订单个 active Proposal，并通过验证后转为 ready |
| `$mdf archive` | 归档终态 Proposal 及 closed/rejected Bug |
| `$mdf prp split` | 拆分未开工 PRP，并完整改写依赖 |
| `$mdf design` | 确认设计、测试策略和共享代码底座 |
| `$mdf write-tests` | 按目标编写可执行测试；不要求全绿 |
| `$mdf implement` | 按已确认设计实现 |
| `$mdf converge` | 收敛：前置 objectives 已勾 + smart，自勾 converge |
| `$mdf fix <bug-id> [--yolo]` | 先确认 failing test，再修复并标为 `fixed` |
| `$mdf bug close <bug-id> --fixed-in <version>` | 验证与审查已 `fixed` 的 Bug，通过后关闭并写入版本 |
| `$mdf verify [arg]` | module 级验证；开发用 smart，closeout 前用 branch |
| `$mdf code-review` | 审查并修复实现、测试和 code smell |
| `$mdf fact update [<path>...] [--scope branch\|full\|paths]` | 按实现对齐当前事实，再修范围内文档结构；closeout 在 verify branch 之后 |
| `$mdf close-out` / `$mdf finish` | 材料与 Gitflow 收口（verify branch / fact 已在主链完成） |
| `$mdf squash [--dry-run]` | 定地板与切段并 soft-reset；`--dry-run` 只给建议 |
| `$mdf fact audit [<path>...] [--scope branch\|full\|paths]` | 只读审阅文档与实现的覆盖、证据、语义与加载质量 |
| `$mdf prettify [<path>...] [--scope branch\|full\|paths]` | 按文档结构规则把大段文字改写为列表、表格与图，不改语义 |
| `$mdf clarify <议题>` | 压力测试计划、决策或想法 |
| `$mdf upgrade` | 从上游拉取最新 Skill 并替换已安装副本 |
| `$mdf to <target>` | 进入目标 worktree；`plan` 进 planning，`develop` 回主树，`deploy` 检出 master |
| `$mdf sync` | 先拉后推 `master` / `develop` / `planning`；其他分支只报告 |
| `$mdf integrate` | 同仓走角色与验收，不开消息通道；跨仓才收发消息；一侧只 poll 本侧 |

裸 `$mdf` 与 `$mdf help` 显示帮助目录。

### 主线流程

主线 intent 由用户手动触发。

- `$mdf next`：单步续办。
- `$mdf deliver`：从 start 持续到 close-out。

统一骨架：

`start → [design?] → 开发 → converge → code-review → verify branch → fact → close-out`

- 是否 design 由 start clarify 冻结的 `needs_design` 决定。
- converge 做 smart 验收；verify branch 为独立阶段。
- 一个 feature 对应一个 PRP；`needs_design: yes` 时 design 提交共用底座。
- start 始终独立 worktree。
  - write-tests 与 implement 在 roster ≥1 时强制独立 worktree，`0,0` 时在 owner 上做。

### code-review 与 roster

code-review 支持 feature、bugfix、hotfix 和 release。

- 首轮按冻结的 roster.reviewers 个 subagent 覆盖起点到当轮 tip。
- 后续增量只审相对操作左端点以来的改动，并复核上轮问题；裁定收口时洗成无
  commit 的 `code-review.md` 终稿。
- 默认每人全范围（replicate），也可切片审查（partition）。
- 主 Agent 汇总裁定、修复并复核。
- 前三种分支从固定起点审查，release 从上一正式发布版本审查。
- qa/dev 默认 best-of-n，也可在 design 按 partition 分工。
- `$mdf start` / `deliver` 可带 `--roster`（solo / min-tdd / competing-pair / coop-pair）。
- `$mdf start` / `design` / `deliver` / `code-review` 可带以下参数：
  - `--qa-strategy`、`--dev-strategy`、`--review-strategy`。
  - `--write-tests-model`、`--implement-model`、`--code-review-model`；
    值为口语描述，可点名一个或多个模型。

### finish 与 deliver

finish 先在交付分支集成 develop（feature/bugfix）或 master（release/hotfix），冲突自动尝试解决。

- 集成产生新提交后：
  - 仅非本交付 `docs/` 增量则跳过 code-review 与所需 suite。
  - 否则走 1 人增量新一轮 code-review 与所需 suite，再继续收口。
- release/hotfix 的 finish 包含 tag 与发版推送。
- deliver 对可并行的 write-tests 与 implement 按 roster 强制分别分派 subagent。
  - 验证其已有 qa/dev worktree 身份，等待交接后再收敛。
- design 的 Baseline 与 converge 由各 intent 自行派恰好 1 个 owner subagent，不计入 roster。
- deliver 尚未 start 时先委托 start。
- 可传位置参数 target（PRP 或 Bug ID，自动分辨）。
- 需要用户决定时暂停。
- 自裁定模式：
  - `--auto-pilot` 由 Agent 自裁定，仅在合入目标主线并删除源分支前确认。
  - `--yolo` 同等自裁定且跳过该确认。
  - 死硬阻塞仍停止。
  - finish 保留 detached worktree；Agent 收尾后另行询问是否删除，所有模式都须明确确认。
    确认删除后结束本对话，后续工作在主 worktree 开新对话。
- release 从 develop 开分支前确认发布目标。
  - 工作线三选一；目标里只写选中的那条。不实施新 PRP。
  - 不联调：`start → [design?] → 开发 → converge → code-review → verify branch →
    fact audit → close-out`。开发/converge 用 smart；branch 验证与 fact 在 code-review 之后。
  - 同 worktree（同仓）：对齐计划、两端验收、确认不再改代码后才审查。不打开消息通道。
  - 跨 worktree（跨仓）：开通道、对齐计划、本端/双端验收、确认不再改代码后才审查。
  - 跨 worktree 每侧只改本仓；可启动本侧依赖（如数据库）；不得改、操作、启动或终止对端。
  - fact audit（必要时 fact update）在 verify branch 之后、close-out 之前。
    Goal 完成前，用户没让你停，永远不许停下来。
  - code-review 基线仍为上一正式发布。

### 写入分支与提交

规划写入共用一个 `planning` 分支与 worktree。

- 写入型 intent 允许并鼓励主动本地提交，包括如实标注状态的阶段成果。
  - 提交不代表验收通过，也不替代用户确认。
  - 不夹带无关改动，远端与集成操作按各自流程授权。
- ❌ 正常工作不在 master 直接修改或提交。
- 规划写入在唯一的 `planning` 工作区进行，合入 develop。
  - 与当前交付分支工作相关的文档在该分支更新。
- 新建 Proposal 只能在 planning 上分配 ID、写入并提交，再合入 develop。
- 初始化和发布合并按专门流程执行；只读操作不受写入分支限制。
- 材料自 start 起位于 `changes/unreleased/<slug>/`。
  - CHANGE.md 在同级目录于交付完成时补齐，再随版本归档。

### 契约与初始化

MDF 仅实现当前契约：不识别、维护或兼容历史 Skill、目录或调用形式。

- 协议、工具与 schema 版本均为数字 `3`。
- manifest 或 `docs/` 布局不符合当前契约时，doctor 只给出指向 `$mdf migrate` 的 finding。
  - 由 migrate 一次性收敛，不提供旧版运行分支。
- init、bootstrap 与 migrate 都负责项目 Git 化，准备本地 master/develop，不强制远端。
- bootstrap 不搭建业务工程或测试，也不调用 fact audit。
  - 发现已有实际实现或运行事实时，在写入前停止并提示 migrate。
- init 按状态转入 bootstrap 或 migrate。
- 校验通过并经用户确认启用后进入 ready。
- 入口先识别已有改动，仅在具体操作需要时要求 clean。

## 信息分层

| 类型 | 载体 |
| --- | --- |
| 用户入口 | 根 `README.md`：项目是干什么，并链到 user-guide |
| 文档入口 | `docs/README.md`；维护者按主题只开一份页面 |
| 维护者事实 | `docs/system/`：`overview.md` 路由、切面主题叶、`deviations.md` 与 `testing/` |
| 用户事实 | `docs/user-guide/`：`README.md` 路由 + 主题叶；维护者默认不打开 |
| 决策 | `docs/context/adr/`；只记录理由，按 `adr-<slug>` 打开单份 |
| 工作上下文 | `docs/context/research/` |
| 代码结构 Wiki | `docs/repowiki/`；仅由 CodeWiki MCP 生成与更新，用于按需搜索 |
| 未分诊记录 | `docs/JOTS.md` |
| 意图与工作 | Proposal、Bug、unreleased Change |
| 证据 | 测试、契约、生成物、配置和命令 |
| 项目维护 | `PROJECT.md` |
| Agent 指令 | `AGENTS.md`、`.mdf/manifest.yaml` |
| 领域术语 | `GLOSSARY.md` |

- 维护者事实中的架构问题以 `docs/system/architecture/` 为准。

Proposal/Bug 是计划与偏差，完成后不会自动成为当前事实。

- 当前事实必须可由证据验证，且不得混写未来计划。
- 一条可观察契约只住一页，其他页只链接。
- 文档按角色有行数硬限制，超出由 fact audit 报 `size.hard`，fact update 以拆页或下沉修复。
- fact update / fact audit 的 `--scope`：
  - 默认 `branch`（起点以来实现改动该碰的事实页）；release 的 `branch` 基线为上一正式发布。
  - `full` 整理知识面全树。
  - finish 只用 `branch`/`paths`。

`docs/JOTS.md` 是可随手追加的原始记录本；它不替代 Proposal、Bug 或任务管理。
当一条 Jot 被提升为 Proposal 或 Bug 后，原条目会在同一份待提交改动中移除。

具体 intent、对象约束和仓库契约随唯一 Skill 一同安装，位于其内部的
`references/`、`assets/` 与 `scripts/`。

## 安装

请从 MDF 仓库获取完整技能集。先在目标仓库创建 Agent 的 Skills 目录，例如
`.codex/skills`，确认 MDF 源仓库工作区干净后安装：

```bash
mkdir -p /absolute/path/to/target-repository/.codex/skills
./mdf-deploy.sh install --target /absolute/path/to/target-repository
```

- `install` 只从当前 `HEAD` 安装，并在 `mdf/references/.version` 写入完整 commit hash。
  - 目标已有 `mdf` 时终止；维护者升级须先运行 `unistall`，再运行 `install`。
- `diff` 分别显示本地与目标相对该基线的改动。
- 已安装项目可用 `$mdf upgrade` 从上游默认分支拉取并替换已安装 Skill。
  - 同时更新已有 `AGENTS.md` 的 MDF 托管区块。
- 脚本与 upgrade 都不会修改目标仓库的 `.mdf/`、`docs/` 或业务文件。

## 维护

维护环境、验证命令与仓库约束见 [`PROJECT.md`](PROJECT.md)；测试范围和说明见
[docs/system/testing/conventions.md](./docs/system/testing/conventions.md)。
