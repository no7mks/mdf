# MDF CLI：仓库写入命令

调用约定与命令总表见 [MDF 确定性 CLI 参考](mdf-cli.md)。


## `prepare-git`

```bash
python3 skills/mdf/scripts/mdf.py prepare-git --repo /path/to/directory
```

目标已是 Git 根时不改写，JSON `created` 为 false。普通目录执行
`git init --initial-branch=master`，`created` 为 true。位于其他仓库内部时
以 `nested_git` 失败，不嵌套初始化。不提交、不配置用户身份。

## `merge-no-ff`

```bash
python3 skills/mdf/scripts/mdf.py merge-no-ff \
  --repo /path/to/repository --commit develop
```

要求 `--repo` 为 Git 根且 worktree clean。把 `--commit` 解析出的提交
`--no-ff` 合入当前分支。已是祖先时 `merged` 为 false。冲突保留
`MERGE_HEAD`，以 `merge_conflict` 失败，不 abort。

## `init`

```bash
python3 skills/mdf/scripts/mdf.py init --repo /path/to/repository \
  --latest-release 1.2.3 \
  --lint 'ruff check .' --build 'true' \
  --quick 'python3 -m pytest -m quick' --smoke 'python3 -m pytest -m smoke' \
  --release 'python3 -m pytest -m release' --budget quick=45 \
  --implementation-root src \
  --baseline 'glossary=documented' \
  --baseline 'user_guide=documented' \
  --baseline 'system_boundary=documented' \
  --baseline 'architecture=documented' \
  --baseline 'interfaces=documented' \
  --baseline 'data=documented' \
  --baseline 'operations=documented' \
  --baseline 'deviations=documented'
```

仅接受 Git 根目录，且远端默认分支不能是 `main`。

- `--latest-release` 为稳定 SemVer 或 `none`。
- 必须提供八项 baseline：glossary、user_guide、system_boundary、architecture、
  interfaces、data、operations、deviations。
  - 每项格式为 `NAME=documented[:仓库相对路径]` 或 `NAME=not_applicable:原因`。
- `--implementation-root` 可重复，默认 `src`。
  - 每个根目录都会写入 manifest，并在首次初始化时建立为空目录。
- `--lint`、`--build`、`--quick`、`--smoke`、`--release` 都必须提供非空命令。
  - 没有业务检查的空仓库 lint、build 可使用 `git diff --check`。
  - quick、smoke、release 须写出 JUnit XML，占位命令会以 `missing_test_report` 失败。
- `--budget <suite>=<秒数>` 可重复，只接受 quick、smoke、release 的正整数，
  写入 `verification.budgets`。
- `--workflow gitflow|github-flow` 与 `--trunk <分支>` 写入 manifest 的 `workflow: {model, trunk}`。
  - 省略 workflow 等同 `gitflow` 与 `master`，manifest 不写该块，行为不变。
  - trunk 不得占用保留名（develop、planning、feature/、bugfix/、release/、on-demand-release/、hotfix/、support/、adhoc/ 等）。
  - 重跑 init 不得静默改变已有 workflow；变更只经 `workflow switch`。

它创建或更新 MDF 固定 scaffold：

- 包括 `.mdf/manifest.yaml`、托管的 `AGENTS.md` 区块、`docs/system/testing/` 起步页和文档骨架。
- 输出会列出拟创建或更新的文件和 diff。
- 实际写入后 manifest 保持 `initializing`，但会写入提供的 verification 入口，不会切换到 `ready`。
- 后续就绪：
  - migrate intent 经事实复核，bootstrap intent 经起步材料核对。
  - 两者均须校验并取得显式就绪确认，再改 ready、校验并提交。
  - bootstrap 不调用 fact audit。
- Git 化和新旧项目的语义分流由外层 intent 完成，init、bootstrap 与 migrate 共用本 CLI。

## `archive`

```bash
python3 skills/mdf/scripts/mdf.py archive --repo /path/to/repository \
  --epoch 1.2 --dry-run
```

要求 Git 根、有效 manifest、clean worktree 和零个 strict-validation finding。
`--epoch` 指定一个发布切片。命令计算 Proposal/Bug 的移动，以及仓库内
canonical 链接重写。`--dry-run` 仅返回计划；正常运行会应用移动与重写，随后再次
strict validation。后校验失败时保留现场，供人工检查。

## `prp-format`

本命令在 planning 工作区转换未开工 active PRP；不代替 Agent 取得用户确认。

```bash
python3 skills/mdf/scripts/mdf.py prp-format preview --repo /path/to/repository --proposal prp-0001
python3 skills/mdf/scripts/mdf.py prp-format ready --repo /path/to/repository --proposal prp-0001 --confirmed
python3 skills/mdf/scripts/mdf.py prp-format draft --repo /path/to/repository --proposal prp-0001
```

| action | 输入 | 结果 |
| --- | --- | --- |
| `preview` | Markdown draft | 生成同目录 `<stem>.review.html`，不修改对象状态 |
| `ready` | draft、对应 preview、`--confirmed` | 保存唯一 ready HTML，删除 Markdown 与 preview，改写引用 |
| `draft` | 未开工 ready PRP | HTML 转回 Markdown 并改写引用；Markdown 原位改为 draft |

- 要求 Git 根、planning、manifest ready、有效对象及依赖；不要求 clean，不提交。
- preview 必须与当前 draft 一致；缺失或稿件变化以 `preview_changed` 失败。
- 转换校验失败时恢复本次改写；其他异常保留现场并报告实际状态。
- HTML 存储格式、详细内容与展示检查见 [HTML 工作材料](../../../skills/mdf/references/html-materials.md)。

## `release-closeout`

```bash
python3 skills/mdf/scripts/mdf.py release-closeout \
  --repo /path/to/repository --release-date 2026-08-04 --dry-run
```

仅接受 `release/<version>`、`hotfix/<version>` 或 `hotfix/<slug>` 当前分支。

- 要求 Git 根、clean worktree、`manifest.state: ready` 与 strict validation 零 error。
- 必须提供 `--release-date`。
- Core 只验证确定性审计；同次 `$mdf close-out` 的语义审阅与用户确认属于 intent 的职责。

收口输入：

- release 会从所有 `changes/unreleased/*/CHANGE.md` 汇总对象结果。
- hotfix 必须额外提供 `--hotfix-change-json`。
- 可用 `--closures-json` 覆盖或补充收口结果。
- `--deferred-acceptance-json` 记录 deferred 的接受信息。

正常运行的步骤：

1. 验证：
   - 复用条件：已有 `verification-report.json` 声称通过，且命令序列与当前 lint、build、quick、
     所需 smoke/release suite 一致（不对照 HEAD）。release 序列含 `playbook:<路径>` 条目。
   - 满足时直接复用其结果，输出 `verification.reused` 为证据路径。
   - 否则返回 `verification_report_not_reusable`；不在 closeout 内运行验证命令。
2. 随后保持 worktree clean 后写入版本 Change、归档对象和链接重写。
3. 在最后再次执行 strict validation；后校验失败时 details 含 `findings` 与已写入路径 `written`。

`--dry-run` 不执行验证命令或写入。

## `start`

```bash
python3 skills/mdf/scripts/mdf.py start --repo /path/to/repository \
  --kind feature --proposal prp-0001 --objectives-file /tmp/objectives.md
```

`--kind` 为 `feature`、`bugfix`、`release`、`hotfix` 或 `adhoc`：

| kind | 必需参数 | 禁止 | 基线 |
| --- | --- | --- | --- |
| `feature` | `--proposal` 与 `--objectives-file`；slug 由 PRP 文件名决定 | `--name` | 本地 `develop` |
| `bugfix` | `--bug <Bug ID>`；分支名为 `bugfix/<Bug ID>` | `--name` | 本地 `develop` |
| `release` | 稳定 SemVer 的 `--version` 与 `--objectives-file` | — | 本地 `develop` |
| `hotfix` | `--version <semver>` 或 `--name <slug>`；slug 可另传 `--version` | `--objectives-file` | 本地 `master` |
| `adhoc` | `--name <名称>`；自动生成六项 objectives | PRP、Bug、版本、manual、objectives 文件 | 本地 `develop` |

github-flow（manifest 的 `workflow.model`）下基线改为 `workflow.trunk`，没有 develop：

- feature、bugfix、release、hotfix、adhoc 均从 trunk 建分支并回到 trunk；`--from-master`、to develop、ODR 与 `dev-pr` 被拒绝。
- `--from-commit <sha>`：release 的历史切点。要求位于 trunk 第一父链且晚于上一发布 tag；创建即冻结，之后不随 trunk 前进，
  禁止 catch-up 引入切点之后的提交；发布以固定的 `release_head` 打 tag，并核验其为 `<trunk>` 的 ancestor。
- `--support <major.minor>`：hotfix 的维护线。多条发布线并存时必须显式指定；首次使用惰性切出 `support/<major.minor>`
  并同步 manifest 配置。support hotfix 只发布到 support 线、永不合入 trunk，每个已修 Bug 须记录 Trunk-First 处置
  （`backported`、`trunk_not_affected`、`urgent_support_first`；后两者须写理由）。

命令要求 clean worktree 和本地基线分支存在。不要求 origin，不 fetch、不 push。
有 origin 时用 `ls-remote` 核对基线。远程提交必须已在本地，本地可以更新。

分支与 worktree：

- 若新分支在本地已存在则失败，不检查远端。
- 始终从基线在仓库同级 `<repo-name>-worktrees/<worktree-name>` 建立 worktree，路径等于分支名。
  - 不在当前目录开分支。
- 成功 JSON 含该 `worktree`、冻结后的 `roster` 与 `roles` 列表。
- roster ≥1 时按人数建立 `qa/<owner>`、`dev/<owner>`，第 2 路起为 `qa/2/<owner>`。
- 创建失败拆除已建 worktree 与分支。
- 成功后的可选 hook 见 [post-gitflow-start](../../../skills/mdf/references/hooks/post-gitflow-start.md)。
  - command 由 Core 执行，rule 以 `hook.status: pending` 交给 Agent；失败只汇报。

roster 参数：

- `--roster` 为 `solo` / `min-tdd` / `competing-pair` / `coop-pair`。
  - feature 默认 `min-tdd`（`1,1,2`）。
  - release 默认 `solo` 但 reviewers 为 3、review 为 `partition`。
  - bugfix 与 hotfix 默认 `solo`（`0,0,1`）。
  - adhoc 固定 `solo`（`0,0,1`），不接受其他人数或 named roster。
- 省略时按 kind 展开；再叠 `--qa` / `--dev` / `--reviewers` 与策略细项。
  - 一侧为 0 另一侧 ≥1 时把 0 抬成 1。
- `--qa-strategy` / `--dev-strategy` 默认 `best-of-n`，可选 `partition`。
- `--review-strategy` 默认 `replicate`，可选 `partition`。
- `--write-tests-model` / `--implement-model` / `--code-review-model` 各为一句可选口语描述。
  - 可点名一个或多个模型，按 intent 写入 `roster.models`；省略某 flag 则不写该键。
  - 含空格时整句作为一个 token。
- 这些参数对应 start/design/deliver/code-review 的 intent 参数，由 Agent 传入本命令冻结。

Git config 与材料：

- 在本地 Git config 的 `branch.<完整分支名>.mdf-start-commit` 保存完整起点 hash，
  供 bugfix/hotfix code-review 读取。
- 并以 `branch.<owner>.mdf-roster` 冻结人数与策略。
- 不设置 upstream。分支删除时配置随分支清理。
- feature 写入 `changes/unreleased/<slug>/objectives.md` 时，把仓根风格的本地链接改成
  相对该目录的路径。
- release 同样写入 `changes/unreleased/<semver>/objectives.md` 与 `delivery.json`，与 roster 无关。

## `planning`

```bash
python3 skills/mdf/scripts/mdf.py planning ensure --repo /path/to/repository
python3 skills/mdf/scripts/mdf.py planning land --repo /path/to/repository
```

- `ensure` 从本地 `master` 创建或复用唯一的 `planning` 分支，以及仓库同级
  `<repo-name>-worktrees/planning` worktree；不在当前目录开分支。
  - 若该 worktree clean，则把 `master` 合入 `planning`。
    可 fast-forward 时用 ff；已分叉时 no-ff。
  - JSON 含 `worktree`、`created`、`synced`。
- `land` 先检查 planning、master、develop 占用者 clean；planning 合入 master，再将 master 合回 develop。
  - 合入前在所有模式下检查 planning 未共享尾段；planning 占用者也须 clean。
  - `squash_required` 时按 [squash 契约](../../../skills/mdf/references/squash.md) 自主分析并执行，再重试 land。
  - planning 无交付 start_commit，squash 计划以安全 floor 为 start_commit；PR mode 先核完整文档历史。
  - 可 fast-forward 时用 ff；已分叉时 no-ff。
  - 规划 worktree clean 时再把 `master` 合回 `planning`，规则相同。
- 两种模式均优先 fast-forward、分叉时 merge，始终 no-PR；未被占用的目标建立独立 worktree。
- 冲突 abort。squash 检查会 fetch remote 分支与 tag 来核对共享边界；不 push。
- `planning` 不是 Gitflow 交付分支。
- github-flow 的 local 模式直接使用 clean 的 trunk worktree，不建 `planning` 分支。
  PR mode 的 `planning` 是短命分支：`land` 经 PR 合入 trunk 后清理；合并前依赖它的 start 返回 `planning_pr_pending`。

## `workflow`

```bash
python3 skills/mdf/scripts/mdf.py workflow switch --repo /path/to/repository --model github-flow --trunk main
python3 skills/mdf/scripts/mdf.py workflow ci --repo /path/to/repository --provider github
```

- `switch` 只在空闲态执行：当前位于目标 trunk、worktree clean、无在途交付分支；否则拒绝并说明占用者。
  - 新 trunk 必须包含旧 trunk 的全部历史；切回 gitflow 要求 develop 已存在。
  - 只改 manifest 的 `workflow`，保留历史、分支与 tag；提交由调用方完成。
- `ci` 只读，按当前 workflow 返回需触发 CI 的分支（gitflow 为 develop 与 trunk；github-flow 为 trunk 与 `support/*`）
  及对应 provider 的渲染内容。

## `release-integrate`

```bash
python3 skills/mdf/scripts/mdf.py release-integrate --repo /path/to/repository [--source release/1.2.3]
```

仅 github-flow 的 PR mode：release 与最新 `origin/<trunk>` 冲突时，在独立 `codex/integrate/release-<semver>` 分支合并并解决冲突，
再以该分支走 PR。发布仍以原 release 的固定 `release_head` 打 tag；集成分支不改变 `release_head`，也不产生回合。

## `to`

```bash
python3 skills/mdf/scripts/mdf.py to --repo /path/to/repository --target plan
```

- 要求 Git 根，不要求 manifest 或 clean worktree。
- `plan` / `planning` / `plan-mode` 内部 `planning ensure`。
- `develop` 复用占用 develop 的 worktree，不新建。
- `deploy` 创建或复用 `<repo-name>-worktrees/deploy`，检出已有 `master`。
  - 已跟踪改动干净才切回 master；gitignore 的文件保留。
  - master 不存在或已被占用则失败。不新建分支，close-out 不拆除。
- 已有 worktree 按分支名或目录名复用；已有本地分支缺树则
  `worktree add` 到 `<repo-name>-worktrees/`。
- ❌ 不创建新分支。
- JSON 含 `target`、`alias`、`branch`、`worktree`、`created`。

## `sync`

```bash
python3 skills/mdf/scripts/mdf.py sync --repo /path/to/repository
```

要求 Git 根与 `origin`；不要求 manifest 或 ready。固定对齐
`master`、`develop`、`planning`：

1. 默认 `fetch --prune` 后仅预览；三大分支本地与 `origin/<branch>` 都必须已存在。
   - JSON `branches` 含所有分支的 local / remote SHA、ahead / behind、relation、graph 与 sync。
   - graph 折叠 commit 路径但始终保留双方 tip；diverged 表示可能 conflict。
   - 用户确认后传 `--confirm <confirmation>` 执行；绑定目标仓库、origin fetch / push URL 与 tip。
     再次 fetch 后任一绑定项变化则以 `sync_plan_changed` 返回新预览，须重新确认。
2. 占用任一 trunk 的 worktree 须干净；某 trunk 无占用者时主 worktree 须干净。
3. 按序对三大分支 pull：远端已是祖先则 noop；可 ff 则 `--ff-only`；已分叉则
   `--no-ff` 合并并提交 `chore(sync): 合并 origin/<branch> 到 <branch>`。
4. 三大分支全部 pull 成功后，以完整 refspec 原子 push 三者，显式 `--no-follow-tags`。
5. 执行 JSON 含各 trunk 的 `pull` / `push`，以及只读的 `extra_local` / `extra_remote`。

PR mode 的受保护增量：

- 默认预览的 `pull_plan` 列出 master/develop 的 PR/MR 计划；普通确认执行返回 `pr_required`。
- `sync --repo <repo> --pr` 预览，带同模式的 `--confirm` 才创建或恢复 PR/MR。
  - confirmation 另绑定 PR 模式与恢复记录；恢复数据位于 Git common dir 的 `mdf/finish/sync/`。
- JSON `status: waiting_for_pr` 含各 target 的 `pull_requests`；不继续 pull/push 三大 trunk。
- 平台 merge commit 核验后仅同名 ff 本地；所有 PR 完成返回 `ready_to_sync` 与新 `preview`。
  - 按新预览确认，再继续常规 sync；保留 source branch，无 reset 或自动合并 PR。
- 完整边界见 [Sync 契约](../../../skills/mdf/references/sync.md#pr-提交与恢复)。

conflict 保留 MERGE_HEAD 与 checkout；错误 details 含 branch、worktree、conflicts 和 Git 输出。
Agent 先尝试解决并验证，无法处理才询问用户；解决后提交并重新预览，继续剩余同步。
仅本次已授权的 pull 与 resolution 改变 local tip 且 remote 未变时可继续，否则重新确认。

❌ 不操作多余分支，不 rebase，不 force-push，不删除远端或本地分支。

## `pre-gitflow-finish`

```bash
python3 skills/mdf/scripts/mdf.py pre-gitflow-finish --repo /path/to/repository
python3 skills/mdf/scripts/mdf.py pre-gitflow-finish --repo /path/to/repository --after <before_head>
```

- 在 owner 交付分支、manifest ready、clean 时执行；位置在 branch 验证后、fact 前。
- 详见 [hook 契约](../../../skills/mdf/references/hooks/pre-gitflow-finish.md)。
- JSON 含 `before_head`、`hook`；rule 返回 `hook.status: pending`，交给 Agent 执行。
- command 完成（含失败）后返回 `changed_paths` 与 `needs_recheck`；失败不令 CLI 非零退出。
- `--after` 只比较原 commit 到当前实际改动，不执行 hook，不要求 clean；供 rule 执行后核对。
- 仅普通 Markdown 文档改动可直接进入 fact；其他改动由 Agent 补 code-review 与 branch 验证。
- CLI 不创建提交或执行补审补测；主链 Agent 汇报结果，续办按上下文或 CLI 日志确认已执行，不重跑 hook。
- 不要求新建 Markdown 执行记录；没有实际改动时不制造文档或提交。
- `finish-gitflow` 不触发此 hook；独立 fact 维护与 migrate 不触发。

## `finish-gitflow`

```bash
python3 skills/mdf/scripts/mdf.py finish-gitflow --repo /path/to/repository
```

要求当前分支为支持的交付分支、worktree clean；普通分支归 adhoc，主线及内部角色不独立收口。

- 在 fetch、合并或发布记录写入前，一次性只读检查源与全部目标 worktree。
  feature/bugfix/adhoc 检查 develop；release/hotfix 检查 master、develop。
- 任一工作区有未提交改动或 `MERGE_HEAD` 等未结束操作即以 `dirty_worktree` 停止。
  即使冲突已解决、已 add 或 diff 为空也保留现场；不为 clean 自动 abort、reset、stash 或 Commit。
- 无关分支的脏状态不阻断 close-out，也不被整理。

外层 close-out intent 的前置流程（由 intent 执行，CLI 不代为集成或审查）：

1. 先在交付分支集成 develop（feature/bugfix/adhoc）或 master（release/hotfix），
   由 Agent 自动尝试解决集成冲突。
2. 集成产生新提交后：
   - 仅非本交付 `docs/` 增量则跳过 code-review 与所需 suite。
   - 否则执行 1 人增量新一轮 code-review 与所需 suite。
3. 再核对本轮 1 份审查、主 Agent 复核与验证记录。
4. 写入、检查并提交 `delivery-summary.html`；adhoc 的总结直接写入 Change。

非 feature 的语义审查记录由 intent 核对，finish-gitflow 不代替此检查。

feature/bugfix/adhoc：

- 不 fetch、不 push。
- 以 `--no-ff --no-commit` 合并到本地 `develop`，再以
  `chore(gitflow): 合并 <source> 到 <target>` 提交。
  - feature 的 implemented 转换包含在该 merge commit。
  - 有账本 adhoc 要求清单完成；无账本不创建 delivery/objectives，核规范 Change。
  - adhoc Change 可为 adhoc 或 fix，source_branch 保留真实名称且 `proposals: []`；不修改 PRP。
- 角色分支或 worktree 仍在则失败。

adhoc 的状态与恢复：

- `adhoc-status --repo <owner> [--slug <slug>] [--source <source>]` 返回材料模式、目录及实际完成证据。
- 无账本时还返回 range、paths；材料目录冲突不覆盖，smart report 使用同一目录。
- local 以安全 source hash 在 Git common dir 保存最小操作记录，支持 `finish-gitflow --source <source>` 恢复。
  - 恢复核实际双亲 merge、源 tip 与目标第一父链；不重复 merge，不删除重新创建的源 ref。
- 主 worktree 能切回 develop 时切回，否则 detach；独立 owner 保留在交付 tip。
- PR mode 可接管只有规范 Change 的已合并外部 PR；先核平台 source/target/head，再续办清理。

release/hotfix：

1. 要求 origin，先 `fetch --prune`，并要求本地 `master` 与远端完全一致
   （不要求源分支有 upstream）；`develop` 只要求本地 worktree clean，不核对远端。
2. 先同样合并到 `master`，创建带注释的 `v<version>` tag，再把 `master` 合并到 `develop`。
3. 最后原子推送 `master` 和 tag，删除本地源分支；`develop` 仅在本地合回，不推送。
   - 不推送、不删除远端 `release/*`/`hotfix/*`。

通用：

- 合并/发布成功后，将源 worktree 切为 `detached HEAD`，删除本地源分支，保留工作区后退出。
- JSON 含 `retained_worktree`（保留路径，无则为 null）与 `primary_worktree`（主路径）。
- Agent 完成核验与报告后决定是否删除工作区；独立调用须用户确认，deliver 委托按其 confidence 策略裁定。
  - 确认后直接从主 worktree 执行 `git worktree remove`，并说明本对话不要再继续。
  - 不新增清理脚本；拒绝或未决则保留，不影响交付完成。
- ⚠️ 本次新产生的 merge 冲突才会 abort，不会推送或删除分支；Git 拒绝开始合并时保留现场。

## `upgrade`

```bash
python3 skills/mdf/scripts/mdf.py upgrade --repo /path/to/repository --dry-run
python3 skills/mdf/scripts/mdf.py upgrade --repo /path/to/repository --expected-commit <预览commit>
```

要求 Git 根，不要求 manifest、ready 或 clean worktree。

- 上游：
  - 默认源为 `http://10.1.5.65:8929/mars/mdf`，克隆远程默认分支 HEAD，并归档 `skills/mdf`。
  - `--source` 可覆盖上游。
  - 非预览必须传 `--expected-commit`，在写入前比对上游 HEAD。
  - 变化报 `upgrade_source_changed`，须重新预览并确认。
- 写入范围：
  - 命令只替换已存在的 Agent Skills 目录中的 `mdf`，写入 `references/.version`。
  - 并更新已有 `AGENTS.md` 的唯一 MDF 托管区块；无该文件或无区块则跳过，不新建或追加。
  - ❌ 不创建未安装位置，不覆盖 `skills/mdf`，不修改 `.mdf/` 或 `docs/`。
- 提交：
  - 非预览写入后仅提交本次替换路径与已更新的 `AGENTS.md`，不夹带其他改动，不 push。
  - 无变更则不创建提交。
- `--dry-run` 只拉取并报告 `new_commit`、各目标当前基线、`history`、`agents` 与 `commit` 计划。
  - `history` 按已安装 `.version` 分组，列出上游 `skills/mdf` 在该基线到 HEAD 之间的提交与文件变更。
  - 无法对照时带 `status`，不视为失败。


## `bug close`

`bug close <bug-id> --fixed-in <version> --repo <仓库>` 是 bug close intent 验收完成后的状态写入。

- intent 先完成复现验证与修复代码审查；Core 不执行这些语义验收。
- 要求 ready、active fixed Bug、稳定 SemVer；release 上须与分支版本一致，hotfix 须与已固定发布版本一致。
- 写入 status: closed 与 fixed_in，保留 found_in，不提交或归档。

## 无 PRP 的人工 feature

`start --repo <repo> --kind feature --manual --name <slug> --objectives-file <file>`

- `--manual` 仅支持 feature，与 `--proposal`、`--bug`、`--version` 互斥。
- `--name` 为已确认的 kebab-case slug；roster 固定 `0,0,1`。
- objectives 依次为 start、人工工作、lint、code-review、verify smoke、fact update、catch-up。local 模式另含 close-out。
  start 时仅 start 已勾；人工工作由用户显式勾选。
- 创建 owner worktree，写入 `manual: true` 与 `needs_design: false`，不写 proposal。
- finish-gitflow 要求清单全部完成，Change 不引用 PRP；合入 develop 不更新 PRP。
