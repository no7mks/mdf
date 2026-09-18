# MDF 确定性 CLI 参考

`skills/mdf/scripts/mdf.py` 是 MDF intent 调用的确定性 CLI。
本文件列出当前命令、参数和实际效果，供 MDF 仓库维护者审阅与测试。

它不是安装后交付给最终用户的 Skill 材料，也不是
`$mdf <intent>` 的用户帮助。后者是用户 intent；本文件中的 command
是 intent 在需要确定性操作时调用的内部接口。

## 调用约定

```bash
python3 skills/mdf/scripts/mdf.py <command> [options]
```

- 成功时命令向 stdout 输出 JSON；业务规则拒绝时输出 JSON 错误，
  并以非零状态退出。
- `--repo` 接受目标仓库路径。除 `info`、`make-id --type bug`、`make-jot-id`、
  `branch --name`、`semver-check` 和 `prepare-git` 外，命令会按自身需要检查 Git
  根、MDF manifest 或 clean worktree。`prepare-git` 接受普通目录；已是其他仓
  库内部路径时失败，不嵌套 `git init`。`make-id --type proposal` 需要 Git 根
  且当前分支为 `planning`。`upgrade` 要求 Git 根，不要求 manifest 或 clean
  worktree。
- 对象写入类 CLI 本身不创建提交；外层写入型 intent 允许并鼓励主动本地提交，
  包括如实标注状态的阶段成果，不夹带无关改动，不替代用户确认或验收。
  start、delivery integrate、finish-gitflow、planning、upgrade 与 `merge-no-ff`
  按各自协议执行提交、集成和远端操作。
- `--dry-run` 只在 `archive`、`prp-split`、`release-closeout` 和
  `upgrade` 中有效。

## 命令表

| 命令 | 类别 |
| --- | --- |
| `info` | 版本信息 |
| `doctor` | 仓库状态 |
| `prepare-git` | 非 Git 目录初始化为 master |
| `merge-no-ff` | 在当前分支 no-ff 合并指定提交 |
| `init` | 初始化写入 |
| `validate` | 确定性校验 |
| `fact-audit` | 确定性审计 |
| `make-id` | 对象 ID |
| `make-jot-id` | Jot ID |
| `branch` | 分支解析 |
| `semver-check` | 版本校验 |
| `archive` | 对象归档 |
| `release-closeout` | 版本收口 |
| `start` | 创建分支 |
| `list` | 对象清单 |
| `tree` | draft/ready 混态依赖视图 |
| `prp-split` | 未开工 PRP 拆分 |
| `delivery` | 阶段 gate 与验证 |
| `worktree-check` | 分派路径、角色与交接核验 |
| `project-verify` | 非 feature 全量验证与证据检查 |
| `codewiki-runtime` | 本地 CodeWiki 运行时准备 |
| `planning` | 规划工作区 |
| `finish-gitflow` | Gitflow 合并 |
| `upgrade` | 替换已安装 Skill |

## 只读命令

### `info`

```bash
python3 skills/mdf/scripts/mdf.py info
```

输出 `tool_version`、`protocol_version` 和 `schema_version`。当前三者都必须为
数字 `3`；intent 以此拒绝错误或不兼容的 CLI。

### `doctor`

```bash
python3 skills/mdf/scripts/mdf.py doctor --repo /path/to/repository
```

报告目标路径的 Git 根、是否为 Git 根、worktree 是否 clean，及当前分支的
解析结果。它还报告 `.mdf/manifest.yaml` 是否存在和 manifest 校验 findings。
已初始化仓库会给出 manifest state；只有 state 为 `ready`
且没有 finding 时，`normal_workflows_allowed` 才为 `true`。进行中的
`changes/unreleased/<slug>/` 只要有 `delivery.json`，缺少 CHANGE.md
不构成 finding。`schema_version` 不是当前值报 `manifest.schema`；`docs/product/`
或 `docs/adr/` 目录存在报 `layout.migrate`；两者都指向 `$mdf migrate`。clean 单独
报告，由具体操作决定是否要求，不作为正常工作流的统一门槛。

### `validate`

```bash
python3 skills/mdf/scripts/mdf.py validate --repo /path/to/repository \
  --scope targeted
```

`--scope` 可为 `targeted`（默认）或 `full`。两者都校验 MDF 确定性契约；
`full` 额外执行全量检查。存在 finding 时仍输出完整 JSON 结果，
但以状态码 `2` 失败。

### `fact-audit`

```bash
python3 skills/mdf/scripts/mdf.py fact-audit --repo /path/to/repository
```

`--scope` 可为 `full`（默认）、`branch` 或 `paths`。

全量审计遍历 manifest 的 `implementation_roots` 与全部当前事实文档，输出实现范围、
文档—`evidence` 映射、ignore 匹配、warnings 和 findings。未被 evidence 覆盖的实现
文件是 warning，不会令命令失败；结构、范围、证据与 ignorelist 错误是 finding，并以
状态码 `2` 失败。它不执行 `verification.commands`，不判断文本语义，也不写入文件。

它同时按文档角色检查体积（物理行；`AGENTS.md` 只计托管区块）：路由页
（`docs/README.md`、`docs/user-guide/README.md`、`docs/system/overview.md`、切面
`index.md`）、`AGENTS.md` 托管块与 `PROJECT.md` 为 100；根 `README.md` 为 200；
`docs/user-guide/`、`docs/system/` 主题叶 450；`docs/context/adr/` 300；Proposal、
Bug、`docs/JOTS.md` 为 500。超出为 `size.hard` finding。`full` 检查全部带角色
文档；`branch`、`paths` 只检查范围内文档与本次改动到的入口页。

分支范围审计以 `--base` 指定起点 commit（省略时取 `merge-base develop HEAD`），
实现范围是起点以来改动的实现文件，文档范围是改动到的事实页与 evidence 引用这些实现
的事实页，结果含 `base`。`--base` 可以是 commit 或 tag；finish release 传入上一
正式发布：

```bash
python3 skills/mdf/scripts/mdf.py fact-audit --repo /path/to/repository \
  --scope branch --base <start_commit>
python3 skills/mdf/scripts/mdf.py fact-audit --repo /path/to/repository \
  --scope branch --base v1.2.0
```

范围审计使用精确路径清单：

```bash
python3 skills/mdf/scripts/mdf.py fact-audit --repo /path/to/repository \
  --scope paths --implementation-path src/service.py \
  --document-path docs/system/interfaces/api.md
```

### `list`

```bash
python3 skills/mdf/scripts/mdf.py list --repo /path/to/repository \
  --type bug --status open
python3 skills/mdf/scripts/mdf.py list --repo /path/to/repository \
  --type proposal --status draft --status ready --milestone 阶段一
```

只读列出 `docs/proposals/` 与 `docs/bugs/` 顶层的 active 对象，不含 `archive/`。
要求 Git 根与 manifest 存在，不要求 `ready` 或 clean。`--type` 为 `proposal` 或 `bug`，
省略时两者都列；`--status` 可重复，须是所选类型的合法状态；`--milestone` 只适用于
Proposal，`--severity` 只适用于 Bug，两者不能同时使用；与 `--type` 冲突时以
`invalid_filter` 失败。

每条 `objects` 含 `id`、`type`、`status`、`title`（正文首个一级标题）与 `path`。
Proposal 额外给出 `depends_on`、`blocked_by`（未满足的直接依赖，含归档 Proposal 的
状态判断）、`in_progress`（当前工作区或任一 feature 分支存在该 PRP 的开工记录）与
`milestone`；Bug 额外给出 `severity`、`found_in`、`fixed_in`、`reject-reason` 与
`duplicate_of`，缺失字段为 `null`。frontmatter 损坏、文件名不合规或缺少 `id`/`status`
的 active 文件不使命令失败，而是列入 `skipped` 并附原因；契约校验仍由 `validate` 负责。

### `make-id`

```bash
python3 skills/mdf/scripts/mdf.py make-id \
  --type proposal --repo /path/to/repo --slug service-health
```

`--type` 只能是 `proposal` 或 `bug`。`--slug` 必须为 ASCII kebab-case，且不得与
对象 ID 同形。命令生成新的对象 ID，并输出相应的 `prp-...` 或 `bug-...` 标识符和
Markdown 文件名。
Proposal ID 为 `prp-` 加自增序号：1–999 固定三位（`prp-001`），1000 起不再补零
（`prp-1000`）。`make-id --type proposal` 必须提供 `--repo`，在 `planning` 上扫描
`docs/proposals/`（含 archive）已有文件名，取最大序号加一。Bug 与 Jot 仍为类型前缀加
四位字符；每一位从大写英文字母（排除 `I`、`O`）与数字 `2` 至 `9` 中选择。新生成的
四位字符至少包含一个字母和一个数字。完整形式如 `prp-001`、`bug-C4D5`、`jot-E6F7`；
沟通时不得省略前缀或只写序号/短码。
它不创建对象文件，也不检查仓库内 slug 是否唯一。

### `make-jot-id`

```bash
python3 skills/mdf/scripts/mdf.py make-jot-id
```

生成一个 `jot-...` 标识符，供 `$mdf jot` 在 `docs/JOTS.md` 中定位原始记录。它不创建或
修改文件。

### `branch`

```bash
python3 skills/mdf/scripts/mdf.py branch --name feature/service-health
```

以 `--name` 解析分支；未提供时从 `--repo` 的当前分支读取。它会输出是否为
支持的 Gitflow 分支，以及分支类型、slug 或版本等结构化详情。两者均未提供时失败。

### `semver-check`

```bash
python3 skills/mdf/scripts/mdf.py semver-check \
  --previous 1.2.3 --candidate 1.3.0 --categories Added,Fixed
```

比较两个稳定 `MAJOR.MINOR.PATCH` 版本。`--categories` 可包含 `Added`、
`Changed`、`Deprecated`、`Removed`、`Fixed`、`Security`，或独占的 `none`；
`--breaking` 声明破坏性变更。命令输出实际与要求的 bump 类型；候选版本不足，
或 `Removed` 未声明 `--breaking` 时以状态码 `2` 失败。

## 仓库写入命令

### `prepare-git`

```bash
python3 skills/mdf/scripts/mdf.py prepare-git --repo /path/to/directory
```

目标已是 Git 根时不改写，JSON `created` 为 false。普通目录执行
`git init --initial-branch=master`，`created` 为 true。位于其他仓库内部时
以 `nested_git` 失败，不嵌套初始化。不提交、不配置用户身份。

### `merge-no-ff`

```bash
python3 skills/mdf/scripts/mdf.py merge-no-ff \
  --repo /path/to/repository --commit develop
```

要求 `--repo` 为 Git 根且 worktree clean。把 `--commit` 解析出的提交
`--no-ff` 合入当前分支。已是祖先时 `merged` 为 false。冲突保留
`MERGE_HEAD`，以 `merge_conflict` 失败，不 abort。

### `init`

```bash
python3 skills/mdf/scripts/mdf.py init --repo /path/to/repository \
  --latest-release 1.2.3 \
  --verification-item '{"id":"unit","kind":"unit","command":"python3 -m pytest -q"}'  \
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

仅接受 Git 根目录，且远端默认分支不能是 `main`。`--latest-release` 为稳定
SemVer 或 `none`。必须提供 glossary、user_guide、system_boundary、
architecture、interfaces、data、operations、deviations 这八项 baseline。
`--implementation-root` 可重复，默认 `src`；每个根目录都会写入 manifest，并在首次
初始化时建立为空目录。
每项格式为 `NAME=documented[:仓库相对路径]` 或
`NAME=not_applicable:原因`。
至少提供一次 `--verification-item`；可重复提供。没有业务检查的空仓库可使用
`git diff --check`。

它创建或更新 MDF 固定 scaffold，包括 `.mdf/manifest.yaml`、托管的
`AGENTS.md` 区块和文档骨架。输出会列出拟创建或更新的文件和 diff；实际写入后
manifest 保持 `initializing`，但会写入提供的 verification commands，不会切换到
`ready`。migrate intent 经事实复核，bootstrap intent 经起步材料核对；两者均须校验并取得
显式就绪确认，再改 ready、校验并提交。bootstrap 不调用 fact audit。
Git 化和新旧项目的语义分流由外层 intent 完成，init、bootstrap 与 migrate 共用本 CLI。

### `archive`

```bash
python3 skills/mdf/scripts/mdf.py archive --repo /path/to/repository \
  --epoch 1.2 --dry-run
```

要求 Git 根、有效 manifest、clean worktree 和零个 full-validation finding。
`--epoch` 指定一个发布切片。命令计算 Proposal/Bug 的移动，以及仓库内
canonical 链接重写。`--dry-run` 仅返回计划；正常运行会应用移动与重写，随后再次
full validate。后校验失败时保留现场，供人工检查。

### `release-closeout`

```bash
python3 skills/mdf/scripts/mdf.py release-closeout \
  --repo /path/to/repository --release-date 2026-08-04 --dry-run
```

仅接受 `release/<version>` 或 `hotfix/<version>` 当前分支；要求 Git 根、
clean worktree、`manifest.state: ready` 与 full validation 零 finding。
必须提供 `--release-date`。Core 只验证确定性审计；同次 `$mdf finish` 的语义审阅
与用户确认属于 intent 的职责。

release 会从所有 `changes/unreleased/*/CHANGE.md` 汇总对象结果；hotfix 必须额外
提供 `--hotfix-change-json`。可用 `--closures-json` 覆盖或补充收口结果，
`--deferred-acceptance-json` 记录 deferred 的接受信息。正常运行会执行 manifest
声明的验证命令，保持 worktree clean 后写入版本 Change、归档对象和链接重写，并在
最后再次 full validate；`--dry-run` 不执行验证命令或写入。

### `start`

```bash
python3 skills/mdf/scripts/mdf.py start --repo /path/to/repository \
  --kind feature --proposal prp-001 --objectives-file /tmp/objectives.md
```

`--kind` 为 `feature`、`bugfix`、`release` 或 `hotfix`。
`feature` 必须有 `--proposal` 与 `--objectives-file`，slug 由 PRP 文件名决定，
禁止 `--name`。`bugfix` 必须有 `--bug <Bug ID>`，分支名为 `bugfix/<Bug ID>`，
禁止 `--name`。
`release` 与 `hotfix` 必须有稳定 SemVer 的 `--version`。命令要求 clean worktree
和本地基线分支存在。不要求 origin，不 fetch、不 push。

feature、bugfix 和 release 从本地 `develop` 创建，hotfix 从本地 `master` 创建。
若新分支在本地已存在则失败，不检查远端。始终从基线在仓库同级
`<repo-name>-worktrees/<worktree-name>` 建立 worktree，路径等于分支名，
不在当前目录开分支；成功 JSON 含该 `worktree`、冻结后的 `roster` 与 `roles`
列表。`--roster` 为 `solo` / `min-tdd` / `competing-pair` / `coop-pair`：
feature 默认 `min-tdd`，其他 kind 默认 `solo`。省略时按 kind 展开；再叠
`--qa` / `--dev` / `--reviewers` 与策略细项。一侧为 0 另一侧 ≥1 时把 0 抬成 1。
roster ≥1 时按人数建立 `qa/<owner>`、`dev/<owner>`，第 2 路起为
`qa/2/<owner>`。创建失败拆除已建 worktree 与分支。
`--qa-strategy` / `--dev-strategy` 默认 `best-of-n`，可选
`partition`；`--review-strategy` 默认 `replicate`，可选 `partition`。
`--models` 为一句可选描述，省略则不写入。这些参数对应 start/design/deliver/
code-review 的 intent 参数，由 Agent 传入本命令冻结。
在本地 Git config 的 `branch.<完整分支名>.mdf-start-commit` 保存完整起点 hash，
供 bugfix/hotfix code-review 读取；并以 `branch.<owner>.mdf-roster` 冻结人数与策略。
不设置 upstream。分支删除时配置随分支清理。
feature 写入 `changes/unreleased/<slug>/objectives.md` 时，把仓根风格的本地链接改成
相对该目录的路径。

### `planning`

```bash
python3 skills/mdf/scripts/mdf.py planning ensure --repo /path/to/repository
python3 skills/mdf/scripts/mdf.py planning land --repo /path/to/repository
```

`ensure` 从本地 `develop` 创建或复用唯一的 `planning` 分支，以及仓库同级
`<repo-name>-worktrees/planning` worktree；不在当前目录开分支。若该 worktree
clean，则把 `develop` no-ff 合入 `planning`。JSON 含 `worktree`、`created`、
`synced`。`land` 要求占用 `develop` 的 worktree clean，把 `planning` no-ff 合入
`develop`；规划 worktree clean 时再把 `develop` 合回 `planning`。冲突 abort。
不 fetch、不 push。`planning` 不是 Gitflow 交付分支。

### `finish-gitflow`

```bash
python3 skills/mdf/scripts/mdf.py finish-gitflow --repo /path/to/repository
```

要求当前分支为支持的 Gitflow 交付分支、worktree clean。
外层 finish intent 先在交付分支集成 develop（feature/bugfix）或 master（release/hotfix），
由 Agent 自动尝试解决集成冲突；集成产生新提交后执行增量新一轮 code-review 与全量验证，
再核对 roster.reviewers 份审查、主 Agent 复核与验证记录。该前置流程由 intent 执行，CLI 不代为集成或审查；
非 feature 的语义审查记录由 intent 核对，finish-gitflow 不代替此检查。

feature/bugfix 不 fetch、不 push；以 `--no-ff --no-commit` 合并到本地 `develop`，
再以 `chore(gitflow): 合并 <source> 到 <target>` 提交；feature 的 implemented
转换包含在该 merge commit。角色分支或 worktree 仍在则失败。
release/hotfix 要求 origin，先 `fetch --prune`，并要求本地 `master` 与 `develop`
与远端完全一致（不要求源分支有 upstream）。先同样合并到
`master`，创建带注释的 `v<version>` tag，再把 `master` 合并到 `develop`。最后
原子推送 `master`、`develop` 和 tag，删除本地源分支。不推送、不删除远端
`release/*`/`hotfix/*`。若 `--repo` 位于
`<repo-name>-worktrees/` 下，合并后移除该 worktree。任一 merge
冲突都会立即 abort，不会推送或删除分支。

### `upgrade`

```bash
python3 skills/mdf/scripts/mdf.py upgrade --repo /path/to/repository --dry-run
python3 skills/mdf/scripts/mdf.py upgrade --repo /path/to/repository --expected-commit <预览commit>
```

要求 Git 根，不要求 manifest、ready 或 clean worktree。默认源为
`http://10.1.5.65:8929/mars/mdf`，克隆远程默认分支 HEAD，并归档 `skills/mdf`。
非预览必须传 `--expected-commit`，在写入前比对上游 HEAD；变化报
`upgrade_source_changed`，须重新预览并确认。`--source` 可覆盖上游。命令只替换已存在的 Agent Skills 目录中的 `mdf`，写入
`references/.version`，并更新已有 `AGENTS.md` 的唯一 MDF 托管区块；无该文件或
无区块则跳过，不新建或追加。不创建未安装位置，不覆盖 `skills/mdf`，不修改
`.mdf/` 或 `docs/`。非预览写入后仅提交本次替换路径与已更新的 `AGENTS.md`，
不夹带其他改动，不 push；无变更则不创建提交。`--dry-run` 只拉取并报告
`new_commit`、各目标当前基线、`history`、`agents` 与 `commit` 计划。`history`
按已安装 `.version` 分组，列出上游 `skills/mdf` 在该基线到 HEAD 之间的提交
与文件变更；无法对照时带 `status`，不视为失败。

## 与 intent 的关系

deliver 是外层 Agent 协调 intent，复用现有 start、delivery 与 finish 命令，
不新增 deliver CLI；负责从尚未 start 起持续委托、并行 subagent 的 worktree
身份核验与结果交接。位置参数 target 与 `--auto-pilot` 由 intent 解释，不是 CLI 参数。

CLI 不负责询问用户、判定文档语义或决定交付范围。它由 intent 在完成这些判断后
调用：`init`、`bootstrap`、`migrate` intent 使用 `doctor`、`init` 与 `validate`；
`tree` intent 用只读 `tree` CLI 展示 draft/ready 混态依赖视图；
`next` intent 在 feature 交付分支上续办该 feature，否则优先续办在途流程，
无在途时内部委托 tree；`$mdf next?` 直接进入 tree，不走 next；
`intake`、`prp create`、`prp review` 与 `prp split` 使用 `doctor`、`planning`、
`list` 与 `make-id`；`bug create` 使用 `doctor`、`list` 与 `make-id`；
`jot` 使用 `make-jot-id`，`jot promote` 另用 `list` 查重；
`archive` intent 使用 `list` 与 `archive`；`start` intent 使用 `list` 与 `start`；
`upgrade` intent 使用 `upgrade`；
`finish` intent 还会调用 `branch`、`list`、`release-closeout` 和
`finish-gitflow`。

`fact-audit`、`validate`、`semver-check` 与 `info` 提供可重复的状态、契约与版本判断。它们是
intent 和测试的确定性基础，不是面向最终用户的直接产品入口。

## Feature 阶段 CLI

feature start 要求 `--proposal <ID> --objectives-file <文件>`，不接受 `--name`；
slug 取自 PRP 文件名。确认的目标文本先从文件读取，
新分支记录固定起点与 slug，写入材料并提交，不 push。缺 PRP、依赖阻塞或已开工时拒绝。

`delivery <action> --repo <仓库>`：

| action | 输入与效果 |
| --- | --- |
| status | 只读列出交付身份、roster、材料位置、阶段记录与 owner/qa/dev worktree 路径 |
| check | `--stage` 指定待进入阶段或 finish，检查前置和证据有效性 |
| record | `--stage` 与非空 `--summary`，写入通过 CLI 检查的语义审查记录 |
| verify | 执行当前交付所需 suite 并记录 `suites`；可用重复 `--item <id>` 做定位运行，所需 suite 记录不能由单项替代 |
| integrate | 按 strategy 合入；best-of-n 且 n≥2 须 winner；partition 全合后清理角色 |
| roster | 更新 strategy / models；design 后不能改 qa/dev strategy |

design record 需要 `--policy-file <JSON>`。未分层格式为
`{"protected_paths":["tests/","pyproject.toml"]}`；分层后必须同时给出
`suites`，例如 `{"protected_paths":["tests/"],"suites":["billing"]}`。
converge/integrate 的测试规则变更需要 `--test-approval <用户确认记录>`；该文本是授权证据，不是自动授权。
阶段值为 design、write-tests、implement、converge、code-review、fact-update。

`tree` CLI 不识别或推进 workflow；在途判断与原流程委托由 next intent 完成。
`tree --repo <仓库> [--depth 3]` 输出 trees、index、hidden；只读，非法依赖失败。
`trees` 为 draft 与 ready 的混态森林：子节点只挂在未满足的 active PRP 下，
milestone 依赖留在 `blocked_by`，不展开为成员边。根按 milestone 组排序：
无 milestone 依赖的无归属根在前，被依赖的组在上，组内按 PRP ID。`index` 为
`{groups, ungrouped}`：每项含 `status`、`depends_on` 与 `blocked_by`；
有 milestone 的按值分组，无归属放入 `ungrouped`。
`prp-split --repo <仓库> --spec-file <JSON> [--dry-run]` 要求当前分支为
`planning`，在完整预检后一次写入拆分结果。
输入包含 source、children、downstream、rationale；children 每项含 filename、id、depends_on、body，
downstream 是全部原下游 ID 到所需子 ID 列表的映射。预览输出候选文件全文，失败不留下部分拆分。
子 PRP 继承原 PRP 的可选 `milestone`；原 PRP 未声明时省略该字段，不写 `null`。

## 分派与验证脚本

`make-id --type proposal --repo <仓库> --slug <子一> --slug <子二>` 支持重复 slug 参数，
一次只读计算连续编号；多项返回 `items`，单项返回 `id` 与 `filename`。不预占编号，
拆分使用该批候选构造 spec，后续身份冲突由预检拒绝，不提前写占位对象。

`worktree-check --repo <角色路径> --owner <owner路径> --role <owner|qa|dev> [--index N]` 只读核验
Git 根、分支绑定、common dir；`--design-commit <hash>` 另核验共同设计，
`--handoff` 要求 clean 与有效阶段指纹；审查者用 `--expected-head <hash>` 固定只读对象。

`project-verify run --repo <仓库>` 按分支执行所需 suite：release/hotfix 跑
全局 full；bugfix 跑全局 quick 加 `changes/unreleased/<slug>/suites.json` 中
已关联的交付 suite。未分层时跑全部项，证据 `suites` 为 `quick` 与 `full`。
`verification.suites` 缺 `quick`、声明 `full` 或引用不存在的 id 为
`manifest.verification` finding。bugfix 缺少关联返回
`missing_delivery_suite`，引用未知 suite 返回 `unknown_suite`；证据只覆盖 quick 时
`check` 返回 `stale_verification`。
结果写入 `changes/unreleased/<slug>/code-review.verification.json`，含
`suites`。feature/bugfix 的 `<slug>` 为交付 kebab-case；release/hotfix
为该分支稳定 SemVer。
`project-verify check` 只读核验输入指纹、分支、suite 及全绿状态；事实/收口文档不改变代码指纹。

`codewiki-runtime [--directory <路径>]` 只在安装目录缺失时 clone，核对源码和 Git 状态，
只补缺失 venv 并检查导入，返回宿主所需 MCP 字段；不修改宿主配置或目标仓库。

`delivery integrate` 在清理前提交 `gates/integration.json`，固定各角色最终提交、
winner 列表及设计指纹。
重复调用核验同一集成后只完成剩余清理；角色引用改变或无法证明已集成时停止。

release/hotfix 的 `finish-gitflow` 在 Git common dir 的 `mdf/finish/<分支>.json` 保存发布进度，
重试核对实际引用，跳过已完成的合并/tag；推送响应丢失时查询远端后继续。
源 worktree 已移除时，可从主 worktree 使用 `--source <原release/hotfix分支>` 恢复清理。
本地/远端被其他操作改变时拒绝恢复；不会强制对齐或覆盖既有 tag。
