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

### `delivery`

`delivery <action> --repo <仓库>`：

| action | 输入与效果 |
| --- | --- |
| status | 只读列出交付身份、roster、材料位置、阶段记录与 owner/qa/dev worktree 路径 |
| check | `--stage` 指定待进入阶段或 finish/close-out，检查前置和证据有效性 |
| record | `--stage` 与非空 `--summary`，写入通过 CLI 检查的语义审查记录 |
| verify | 辅助入口：lint、build、quick + feature 默认 suite（release）；超预算即失败 |
| integrate | 按 strategy 合入；best-of-n 且 n≥2 须 winner；partition 全合后清理角色 |
| roster | 更新 strategy / 按 intent 的 models；design 后不能改 qa/dev strategy |

- design record 需要 `--policy-file <JSON>`，必须同时给出 `protected_paths` 与 named suite 列表 `suites`。
  - 例如 `{"protected_paths":["tests/"],"suites":["billing"]}`。
  - suite 名不得为 lint/build/quick/smoke/release/full。
- converge/integrate 的测试规则变更需要 `--test-approval <用户确认记录>`。
  - 该文本是授权证据，不是自动授权。
- 阶段值为 design、write-tests、implement、converge（无 code-review / fact-update gate）。

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
  - 审查者用 `--expected-head <hash>` 固定只读对象。

### `project-verify`

`project-verify run --repo <仓库>` 按分支依次执行 lint、build、quick 与
smoke（bugfix）或 release（release/hotfix）。证据 `suites` 为 `quick` 加后者。

- bugfix 须有 `changes/unreleased/<slug>/suites.json` 关联 named suite。
  - 缺失返回 `missing_delivery_suite`；Core 不执行 named suite。
- 证据文件缺失或未覆盖所需 suite 时 `check` 返回 `stale_verification`；文件损坏返回 `invalid_delivery`。
- 运行期间 stderr 输出：
  - `[i/N] start <id>`、子进程原文。
  - 可选 30 秒心跳 `[i/N] running <id> (Ns)`。
  - 以及 `[i/N] done exit=<code> (Ns)`。
- suite 超出预算即终止 process group 并失败，details 含 partial tail。
  - 预算默认 quick 30、smoke 300，可由 `verification.budgets` 覆盖。
  - lint、build 与未设预算的 release 不限时。
- 结果写入 `changes/unreleased/<slug>/code-review.verification.json`，含 `suites`。
  - feature/bugfix 的 `<slug>` 为交付 kebab-case；release/hotfix 为该分支稳定 SemVer。
- `project-verify check` 只读核验输入指纹、分支、suite 及全绿状态。
  - 事实/收口文档不改变代码指纹。

### `quick-run`

`quick-run --repo <仓库>` 在任意分支（含 master 与 detached HEAD）依次执行 manifest 的 lint、build、quick。

- 要求 manifest `ready`，否则返回 `manifest_not_ready`。
- 预算、运行目录、stderr 进度与 quick 报告校验同 `project-verify run`。
- 全部入口都运行，单项失败不中断；不写任何证据文件或 gate。
- 结果含 `head`、逐项 `results`（命令、预算、`log`、quick 的 `report`、`passed`）与 `all_passed`。
  - 全部通过时 stdout 输出结果 JSON，退出 0。
  - 任一失败返回 `verify_command_failed`，details 为同一结果，失败项带 `error` 与 `details`。

### 测试报告与 `suite-run`

`delivery verify`、`project-verify run`、`quick-run` 与 `release-closeout` 执行 quick、smoke、release 时：

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

`suite-run --repo <仓库> --name <named suite> --command <命令>` 以同样方式处理 named suite。

- 为 named suite 新建报告目录、运行命令并校验报告。
- 输出命令结果与 `report`；不写 gate。
- 名称不得为 lint/build/quick/smoke/release/full。

### `codewiki-runtime`

`codewiki-runtime [--directory <路径>]` 准备本地 CodeWiki 运行时：

- 只在安装目录缺失时 clone，核对源码和 Git 状态。
- 只补缺失 venv 并检查导入，返回宿主所需 MCP 字段。
- 不修改宿主配置或目标仓库。

### 集成与发布恢复

- `delivery integrate` 在清理前提交 `gates/integration.json`，固定各角色最终提交、
  winner 列表及设计指纹。
  - 重复调用核验同一集成后只完成剩余清理。
  - 角色引用改变或无法证明已集成时停止。
- release/hotfix 的 `finish-gitflow` 在 Git common dir 的 `mdf/finish/<分支>.json` 保存发布进度。
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
这些子命令只用于跨 worktree 联调。同 worktree 联调不调用它们。

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
- `bug-request` 需要 `--observed`、`--expected`、`--repro`、`--impact`。
- 监听不创建 Bug，也不解释 `send` 正文。
