# MDF CLI：交付阶段与验证

调用约定与命令总表见 [MDF 确定性 CLI 参考](mdf-cli.md)。

## Feature 阶段 CLI

本节列出 feature 与 release 交付阶段使用的 CLI。

- feature start 要求 `--proposal <ID> --objectives-file <文件>`，不接受 `--name`；
  slug 取自 PRP 文件名。
  - 确认的目标文本先从文件读取，新分支记录固定起点与 slug，写入材料并提交，不 push。
  - 缺 PRP、依赖阻塞或已开工时拒绝。
- release start 要求 `--version <semver> --objectives-file <文件>`。
  - 确认的发布目标写入 `changes/unreleased/<semver>/`，不 push。
- adhoc start 使用 `--kind adhoc --name <名称>`，CLI 规范化 slug 并直接生成六项 objectives。
  - 不接受 PRP、Bug、版本、`--manual` 或 `--objectives-file`；固定 roster `0,0,1`、`needs_design: false`。
  - 创建 `adhoc/<slug>` 与同级独立 worktree；close-out no-ff 合入 develop，不改 PRP、不 push。
  - Change 的 `change_kind` 可用 adhoc 或 fix；fix 表示小范围修正，仍要求 `proposals: []`。

### `delivery`

`delivery <action> --repo <仓库>`：

| action | 输入与效果 |
| --- | --- |
| status | 只读列出交付身份、roster、材料位置、可选阶段快照与 owner/qa/dev worktree 路径 |
| check | `--stage` 指定阶段或 finish/close-out；**非进度关口**（见下） |
| record | `--stage` 与非空 `--summary`，写入配置/指纹快照；**禁止**当作进度通行证 |
| roster-join | 按 roster strategy 合流 qa/dev；best-of-n 且 n≥2 须 winner；partition 全合后清理角色 |
| roster | 更新 strategy / 按 intent 的 models；design 完成后不能改 qa/dev strategy |
| resolve-version | hotfix owner 固定发布版本；可传 `--version <semver>`，返回 version 与 tag |

- **进度只认** `objectives.md` 勾选；Agent 主链不得用 `record/check` 选型或卡 close-out。
- design record 需要 `--policy-file <JSON>`，必须同时给出 `protected_paths` 与 named suite 列表 `suites`。
  - 例如 `{"protected_paths":["tests/"],"suites":["billing"]}`。
  - suite 名不得为 lint/build/quick/smoke/release/full。
  - 写入的是 **配置快照**，不是进度 gate。
- converge / roster-join 的测试规则变更需要 `--test-approval <用户确认记录>`。
  - 该文本是授权证据，不是自动授权。
- 阶段值为 design、write-tests、implement、converge（无 code-review / fact-update 阶段文件）。
- `check --stage finish`：仅核对交付材料存在（objectives/delivery.json；needs_design 时另须
  design.md）；**不**读 converge 或其他 `gates/*.json`。
- close-out 查 report 交没交（有文件且声称通过）；不做 commit 对齐审判。
- `resolve-version` 要求 clean；写入后提交 `delivery.json`，再关闭 Bug 和生成版本材料。
  - 自动定版、无 tag 阻断与重试规则见 [Hotfix 版本](../../../skills/mdf/references/hotfix-version.md)。

### `tree`

`tree` CLI 不识别或推进 workflow；在途判断与原流程委托由 next intent 完成。
`tree --repo <仓库> [--depth 3]` 输出 trees、index、hidden、diagram 与 table；只读，非法依赖失败。

| 输出 | 内容 |
| --- | --- |
| `trees` | draft 与 ready 的混态森林，规则见下 |
| `index` | `{groups, ungrouped}`，规则见下 |
| `diagram` | unicode 混态树 |
| `table` | Markdown 索引表，无归属行在前，末行报 hidden |

- `trees` 的子节点只挂在未满足的 active PRP 下。
  - milestone 依赖留在 `blocked_by`，不展开为成员边。
- 根按 milestone 组排序：
  - 无 milestone 依赖的无归属根在前。
  - 被依赖的组在上，组内按 PRP ID。
- `index` 每项含 `status`、`depends_on` 与 `blocked_by`。
  - 有 milestone 的按值分组，无归属放入 `ungrouped`。

### `prp-split`

`prp-split --repo <仓库> --spec-file <JSON> [--dry-run]` 要求当前分支为 `planning`，
在完整预检后一次写入拆分结果。

- 输入包含 source、children、downstream、rationale。
  - children 每项含 filename、id、depends_on、body。
  - downstream 是全部原下游 ID 到所需子 ID 列表的映射。
- 预览输出候选文件全文，失败不留下部分拆分。
- 子 PRP 继承原 PRP 的可选 `milestone`；原 PRP 未声明时省略该字段，不写 `null`。

## 分派与验证脚本

本节列出分派、验证、报告与恢复相关的 CLI。

### 批量 ID 与 worktree 核验

- `make-id --type proposal --repo <仓库> --slug <子一> --slug <子二>` 支持重复 slug 参数，
  一次只读计算连续编号。
  - 多项返回 `items`，单项返回 `id` 与 `filename`。
  - 不预占编号；拆分使用该批候选构造 spec，后续身份冲突由预检拒绝，不提前写占位对象。
- `worktree-check` 只读核验 Git 根、分支绑定、common dir。
  - 调用：`worktree-check --repo <角色路径> --owner <owner路径> --role <owner|qa|dev> [--index N]`。
  - `--design-commit <hash>` 另核验共同设计。
  - `--handoff` 要求 clean 与有效阶段指纹。
  - main Agent 替审查者用 `--expected-head <hash>` 固定只读对象。

### `verify`

`verify [arg] --repo <仓库>`：arg 为 smart/branch/named 时按 scope 解析，
其他值按 named suite 名解析。也可显式使用 `--scope smart|branch|named`。
位置参数不与 `--scope` 同用；仅 `named` 可带 `--suites`。

**branch**

- 始终跑 lint、build、quick。
- 再加 smoke（feature/bugfix/hotfix）或 release（仅 release）。
- 证据 `suites` 为 `quick` 加后者。
- 须在 Gitflow 交付分支；执行前 worktree 必须干净。
- bugfix 须有 `changes/unreleased/<slug>/suites.json` 关联 named suite。
  - 缺失返回 `missing_delivery_suite`；Core 不执行 named suite。
- 证据文件损坏返回 `invalid_delivery`。
- 运行期间 stderr 输出：
  - `[i/N] start <id>`、子进程原文。
  - 可选 30 秒心跳 `[i/N] running <id> (Ns)`。
  - 以及 `[i/N] done exit=<code> (Ns)`。
- suite 超出预算即终止 process group 并失败，details 含 partial tail。
  - 预算默认 quick 30、smoke 300，可由 `verification.budgets` 覆盖。
  - lint、build 与未设预算的 release 不限时。
- 结果写入 `changes/unreleased/<slug>/verification-report.json`，含 `suites`，不含 commit。
  - feature/bugfix 与 slug hotfix 的 `<slug>` 为交付 slug；release 与 SemVer hotfix 为分支版本。
- 同入口多命令：默认串行；`modules.yaml` 中 quick/smoke/release 可设
  `parallel: true`（命令数 >5 返回 `too_many_parallel_commands`）。

**smart**

- 不要求交付分支或交付材料；detached HEAD 返回 `detached_head`。
- 结果 `branch` 保留原名；master/main/develop/planning 的 `kind` 为 `unsupported`，其他普通分支归 adhoc。
- 须至少一个 `--module` 或可由 `--paths` 推断的 module。
- 跑涉及 module 的 lint、build、quick；可选 `--test` 追加点名命令。
- 不写 `verification-report.json`；stdout 返回结果 JSON。
- adhoc 例外：smart 成败均保存 `verification-report.json`，scope 仍为 smart。
  - 只跑涉及 module 的 lint/build/quick 与选题，不要求 smoke 或 branch scope。
  - 包括无账本分支；使用 adhoc-status 的材料目录，允许独立 slug，不创建 delivery/objectives。
- `--report-file <路径>`：smart 成败结果仅写入指定文件，替代上述默认写入位置；用于 catch-up 保留基线报告。
  - 相对路径以 repo 为根；必须留在仓库内且不含符号链接，执行验证前检查路径。
  - branch/named 使用该参数返回 `invalid_verify_scope`。

**named**

- 需要 `--suites <名>[,<名>…]`（五个必选入口、可选 coverage 或 `module.named` 中的真 named）。
- 不要求交付分支；不写 `verification-report.json`。
- 固定入口与可选 coverage：命令来自 `.mdf/modules.yaml`（override 或按 module 展开）。
- 真 named：命令来自 `docs/system/testing/<name>.md` frontmatter 的
  `commands`（或简写 `command`）；可选 `parallel: true`（>5 报错）。
- suite 之间按 `--suites` 顺序串行；suite 内可并行。

### 测试报告

`verify` 与 `release-closeout` 执行 quick、smoke、release 与 named 时：

1. 为每次运行新建 `.mdf/reports/<时间戳>-<suite>/`，以 `MDF_REPORT_DIR` 传给命令。
2. 命令结束后解析其中的 JUnit XML，写入 `summary.json`。
3. 把路径与 test case 级汇总记入结果的 `report`。

- lint 与 build 也各建运行目录。
- 每个运行目录保存完整的 `stdout.log`、`stderr.log`，路径记入结果的 `log`。
- `.mdf/reports/` 由其中的 `.gitignore` 忽略，保留 7 天。

以下情况即使退出码为 0 也判失败：

| 情况 | 返回 |
| --- | --- |
| 缺报告 | `missing_test_report` |
| 无法解析 | `invalid_test_report` |
| 不含 test | `empty_test_report` |
| 含 failure、error 或 skipped | `test_report_failed` |

### `codewiki-runtime`

`codewiki-runtime [--directory <路径>]` 准备本地 CodeWiki 运行时：

- 只在安装目录缺失时 clone，核对源码和 Git 状态。
- 只补缺失 venv 并检查导入，返回宿主所需 MCP 字段。
- 不修改宿主配置或目标仓库。

### 集成与发布恢复

- `delivery roster-join` 在清理前提交 `gates/roster-join.json`，固定各角色最终提交、
  winner 列表及设计指纹。
  - 重复调用核验同一合流后只完成剩余清理。
  - 角色引用改变或无法证明已合流时停止。
- release/hotfix 的 `finish-gitflow` 在 Git common dir 的 `mdf/finish/<分支>.json` 保存发布进度。
  - slug hotfix 按 `mdf/finish/<分支>/<start_commit>.json` 保存；同名分支的新交付使用独立记录。
  - 重试核对实际引用，跳过已完成的合并/tag；推送响应丢失时查询远端后继续。
  - 源 worktree 已移除时，可从主 worktree 使用 `--source <原release/hotfix分支>` 恢复清理。
  - 本地/远端被其他操作改变时拒绝恢复；不会强制对齐或覆盖既有 tag。

### `integrate`

```bash
python3 skills/mdf/scripts/mdf.py integrate init --repo /path/to/repository
python3 skills/mdf/scripts/mdf.py integrate peer --repo /path/to/repository \
  --name backend --target /absolute/peer
python3 skills/mdf/scripts/mdf.py integrate send --repo /path/to/repository \
  --to backend --body "看到超时"
python3 skills/mdf/scripts/mdf.py integrate poll --repo /path/to/repository
python3 skills/mdf/scripts/mdf.py integrate listen --repo /path/to/repository
python3 skills/mdf/scripts/mdf.py integrate status --repo /path/to/repository
```

要求 Git 根，不要求 manifest 或 clean worktree，不创建提交。
这些子命令只用于跨 worktree 消息模式；同 worktree 与 collab-mode 不调用它们。

- Agent 使用其支持的后台 Shell 启动 poll 与 listen，保留会话句柄并读取同一后台 Shell 的输出。

| 子命令 | 行为 |
| --- | --- |
| `init` | 创建 `.integration/inbox/` 与 session token，并在 `.gitignore` 写入 `.integration/` |
| `peer` | `--target` 接受绝对路径、`http://host:port`，或本仓 worktree 的分支名 |
| `send` | 省略 `--kind` 时种类为 `send`；本机 path 对端把消息原子写入对方 inbox |
| `listen` | 默认绑 `127.0.0.1:8765`，只接受 POST，把请求落成 inbox 文件后返回已写入 |
| `poll` | 常驻，只读本侧 inbox；stdout 打可读行，见下 |

- `listen` 鉴权：`ping` 不校验 token，其余种类的 `auth` 必须等于本侧 token。
  - listen 保持服务，收到 `end` 不退出。
- `poll` / `send` 的 stdout：时间、谁发给谁、kind，正文单独成行。
  - poll 启动即「等待」，约每 1 分钟再打一次并向已登记对端发 `heartbeat`。
  - send 打印「发出」。
  - 一个进程只 poll 本侧 `--repo` 的 inbox；不得同时 poll 对端。
  - `--timeout` / `--wait` 仅测试：到期打印「超时」；`--wait` 改等待/心跳间隔。
- `courtesy` / `ack` / `heartbeat` 可空正文；`ack` 必须带 `--reply-to`。
- 自动 heartbeat 后，Agent 通过 `send` 执行 [双方状态确认](../../../skills/mdf/references/integration-heartbeat.md)。
- `bug-request` 需要 `--observed`、`--expected`、`--repro`、`--impact`。
- 监听不创建 Bug，也不解释 `send` 正文。


## 可选 coverage

`verify coverage` 调用可选 coverage 入口，配置与统一 JSON 报告见 Skill 的 repository-contract。

- 支持 module 定义与 repo 级完整覆写；未配置返回 configured: false。
- 代码规模检查统一进入 lint；所有 lint 路径保存工具 summary 与完整输出。

## 延迟选择与 ODR

- start 新增 `--from-master`（仅 feature，含 manual）、`--target` 与可重复 `--feature`（仅 ODR）。
- `--kind on-demand-release --version <semver> --feature feature/<slug>` 从 master 创建发布分支。
- `delivery target --repo <owner> --target <develop|on-demand-release/version>` 写入已确认具体目标；调用方提交。
- `delivery checkpoint --repo <ODR>` 返回纳入 ready、pending 与 features，不修改 checklist；不代表发布就绪。
- feature 的 delivery.json 记录 base_branch、target；ODR 记录 features 与 scope 纳入清单。
- 完整执行规则见 [Late-decision](../../../skills/mdf/references/late-decision.md)。

- `delivery scope --repo <ODR> --scope-file <JSON>`：clean owner 上替换非 feature 范围。
- `start --kind on-demand-release` 接受 `--feature` 和/或 `--scope-file`。
- scope 字段、来源限制与 checkpoint 行为见 [Late-decision](../../../skills/mdf/references/late-decision.md)。

- `delivery accept --repo <ODR>`：clean owner 上核对整版验收，更新所选 PRP 为 implemented 并勾选 ODR 统一验收。
  - 要求 ODR 的 lint、code-review、verify branch、fact audit 已勾，整版报告齐全且 release suite 通过。
  - feature → ODR 不要求补齐 source Change 或验收报告，不修改 source checklist。

- ODR 没有 child Change 的贡献由材料目录的 `release-notes.json` 提供 release_notes 分类与 boolean breaking。
  - `delivery accept` 验证声明并在 objectives 记录已纳入 Git 基线；新来源提交不能沿用旧验收。
  - PR 候选重新验收保留本候选 PRP 的 released 状态；已发布或其他版本不能复用。
