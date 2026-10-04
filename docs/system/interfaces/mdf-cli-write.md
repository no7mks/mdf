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

要求 Git 根、有效 manifest、clean worktree 和零个 full-validation finding。
`--epoch` 指定一个发布切片。命令计算 Proposal/Bug 的移动，以及仓库内
canonical 链接重写。`--dry-run` 仅返回计划；正常运行会应用移动与重写，随后再次
full validate。后校验失败时保留现场，供人工检查。

## `release-closeout`

```bash
python3 skills/mdf/scripts/mdf.py release-closeout \
  --repo /path/to/repository --release-date 2026-08-04 --dry-run
```

仅接受 `release/<version>` 或 `hotfix/<version>` 当前分支。

- 要求 Git 根、clean worktree、`manifest.state: ready` 与 full validation 零 finding。
- 必须提供 `--release-date`。
- Core 只验证确定性审计；同次 `$mdf close-out` / `$mdf finish` 的语义审阅与用户确认属于 intent 的职责。

收口输入：

- release 会从所有 `changes/unreleased/*/CHANGE.md` 汇总对象结果。
- hotfix 必须额外提供 `--hotfix-change-json`。
- 可用 `--closures-json` 覆盖或补充收口结果。
- `--deferred-acceptance-json` 记录 deferred 的接受信息。

正常运行的步骤：

1. 验证：
   - 复用条件：已有 `verification-report.json` 声称通过，且命令序列与当前 lint、build、quick、
     release 一致（不对照 HEAD）。
   - 满足时直接复用其结果，输出 `verification.reused` 为证据路径。
   - 否则依次执行这些命令，`reused` 为 null。
2. 随后保持 worktree clean 后写入版本 Change、归档对象和链接重写。
3. 在最后再次 full validate；后校验失败时 details 含 `findings` 与已写入路径 `written`。

`--dry-run` 不执行验证命令或写入。

## `start`

```bash
python3 skills/mdf/scripts/mdf.py start --repo /path/to/repository \
  --kind feature --proposal prp-001 --objectives-file /tmp/objectives.md
```

`--kind` 为 `feature`、`bugfix`、`release` 或 `hotfix`：

| kind | 必需参数 | 禁止 | 基线 |
| --- | --- | --- | --- |
| `feature` | `--proposal` 与 `--objectives-file`；slug 由 PRP 文件名决定 | `--name` | 本地 `develop` |
| `bugfix` | `--bug <Bug ID>`；分支名为 `bugfix/<Bug ID>` | `--name` | 本地 `develop` |
| `release` | 稳定 SemVer 的 `--version` 与 `--objectives-file` | — | 本地 `develop` |
| `hotfix` | 稳定 SemVer 的 `--version` | `--objectives-file` | 本地 `master` |

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

- `ensure` 从本地 `develop` 创建或复用唯一的 `planning` 分支，以及仓库同级
  `<repo-name>-worktrees/planning` worktree；不在当前目录开分支。
  - 若该 worktree clean，则把 `develop` 合入 `planning`。
    可 fast-forward 时用 ff；已分叉时 no-ff。
  - JSON 含 `worktree`、`created`、`synced`。
- `land` 要求占用 `develop` 的 worktree clean，把 `planning` 合入 `develop`。
  - 可 fast-forward 时用 ff；已分叉时 no-ff。
  - 规划 worktree clean 时再把 `develop` 合回 `planning`，规则相同。
- 冲突 abort。不 fetch、不 push。
- `planning` 不是 Gitflow 交付分支。

## `to`

```bash
python3 skills/mdf/scripts/mdf.py to --repo /path/to/repository --target plan
```

- 要求 Git 根，不要求 manifest 或 clean worktree。
- `plan` / `planning` / `plan-mode` 内部 `planning ensure`。
- `develop` 复用占用 develop 的 worktree，不新建。
- `deploy` 创建或复用 `<repo-name>-worktrees/deploy`，检出已有 `master`。
  - 已跟踪改动干净才切回 master；gitignore 的文件保留。
  - master 不存在或已被占用则失败。不新建分支，close-out / finish 不拆除。
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

1. `fetch --prune`；三大分支本地与 `origin/<branch>` 都必须已存在。
2. 占用任一 trunk 的 worktree 须干净；某 trunk 无占用者时主 worktree 须干净。
3. 按序对三大分支 pull：远端已是祖先则 noop；可 ff 则 `--ff-only`；已分叉则
   `--no-ff` 合并并提交 `chore(sync): 合并 origin/<branch> 到 <branch>`。
4. 三大分支全部 pull 成功后，原子 `push origin master develop planning`。
5. JSON 含各 trunk 的 `pull` / `push`，以及只读的 `extra_local` / `extra_remote`。

❌ 不操作多余分支，不 rebase，不 force-push，不删除远端或本地分支。

## `finish-gitflow`

```bash
python3 skills/mdf/scripts/mdf.py finish-gitflow --repo /path/to/repository
```

要求当前分支为支持的 Gitflow 交付分支、worktree clean。

外层 close-out / finish intent 的前置流程（由 intent 执行，CLI 不代为集成或审查）：

1. 先在交付分支集成 develop（feature/bugfix）或 master（release/hotfix），
   由 Agent 自动尝试解决集成冲突。
2. 集成产生新提交后：
   - 仅非本交付 `docs/` 增量则跳过 code-review 与所需 suite。
   - 否则执行 1 人增量新一轮 code-review 与所需 suite。
3. 再核对本轮 1 份审查、主 Agent 复核与验证记录。

非 feature 的语义审查记录由 intent 核对，finish-gitflow 不代替此检查。

feature/bugfix：

- 不 fetch、不 push。
- 以 `--no-ff --no-commit` 合并到本地 `develop`，再以
  `chore(gitflow): 合并 <source> 到 <target>` 提交。
  - feature 的 implemented 转换包含在该 merge commit。
- 角色分支或 worktree 仍在则失败。

release/hotfix：

1. 要求 origin，先 `fetch --prune`，并要求本地 `master` 与 `develop` 与远端完全一致
   （不要求源分支有 upstream）。
2. 先同样合并到 `master`，创建带注释的 `v<version>` tag，再把 `master` 合并到 `develop`。
3. 最后原子推送 `master`、`develop` 和 tag，删除本地源分支。
   - 不推送、不删除远端 `release/*`/`hotfix/*`。

通用：

- 合并/发布成功后，将源 worktree 切为 `detached HEAD`，删除本地源分支，保留工作区后退出。
- JSON 含 `retained_worktree`（保留路径，无则为 null）与 `primary_worktree`（主路径）。
- Agent 完成核验与报告后询问是否删除工作区；所有模式都须用户明确确认。
  - 确认后直接从主 worktree 执行 `git worktree remove`，并说明本对话不要再继续。
  - 不新增清理脚本；拒绝或未决则保留，不影响交付完成。
- ⚠️ 任一 merge 冲突都会立即 abort，不会推送或删除分支。

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
- 要求 ready、active fixed Bug、稳定 SemVer；release/hotfix 上版本须与分支一致。
- 写入 status: closed 与 fixed_in，保留 found_in，不提交或归档。

## 无 PRP 的人工 feature

`start --repo <repo> --kind feature --manual --name <slug> --objectives-file <file>`

- `--manual` 仅支持 feature，与 `--proposal`、`--bug`、`--version` 互斥。
- `--name` 为已确认的 kebab-case slug；roster 固定 `0,0,1`。
- objectives 六项依次为 start、人工工作、code-review、verify smoke、fact update、close-out。
  start 时仅 start 已勾；人工工作由用户显式勾选。
- 创建 owner worktree，写入 `manual: true` 与 `needs_design: false`，不写 proposal。
- finish-gitflow 要求清单全部完成，Change 不引用 PRP；合入 develop 不更新 PRP。
