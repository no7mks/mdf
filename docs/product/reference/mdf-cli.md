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
- `--repo` 接受目标仓库路径。除 `info`、`make-id`、`make-jot-id`、`branch --name` 和
  `semver-check` 外，命令会按自身需要检查 Git 根、MDF manifest 或
  clean worktree。`upgrade` 要求 Git 根，不要求 manifest 或 clean worktree。
- 对象写入类 CLI 本身不创建提交；外层写入型 intent 允许并鼓励主动本地提交，
  包括如实标注状态的阶段成果，不夹带无关改动，不替代用户确认或验收。
  start、delivery integrate、finish-gitflow 与 upgrade 按各自协议执行提交、
  集成和远端操作。
- `--dry-run` 只在 `archive`、`move-change`、`prp-split`、`release-closeout` 和
  `upgrade` 中有效。

## 命令表

| 命令 | 类别 |
| --- | --- |
| `info` | 版本信息 |
| `doctor` | 仓库状态 |
| `init` | 初始化写入 |
| `validate` | 确定性校验 |
| `fact-audit` | 确定性审计 |
| `make-id` | 对象 ID |
| `make-jot-id` | Jot ID |
| `branch` | 分支解析 |
| `semver-check` | 版本校验 |
| `archive` | 对象归档 |
| `move-change` | Change 迁移 |
| `release-closeout` | 版本收口 |
| `start` | 创建分支 |
| `next` | ready 依赖视图 |
| `prp-split` | 未开工 PRP 拆分 |
| `delivery` | 阶段 gate 与验证 |
| `finish-gitflow` | Gitflow 合并 |
| `upgrade` | 替换已安装 Skill |

## 只读命令

### `info`

```bash
python3 skills/mdf/scripts/mdf.py info
```

输出 `tool_version`、`protocol_version` 和 `schema_version`。当前三者都必须为
数字 `2`；intent 以此拒绝错误或不兼容的 CLI。

### `doctor`

```bash
python3 skills/mdf/scripts/mdf.py doctor --repo /path/to/repository
```

报告目标路径的 Git 根、是否为 Git 根、worktree 是否 clean，及当前分支的
解析结果。它还报告 `.mdf/manifest.yaml` 是否存在和 manifest 校验 findings。
已初始化仓库会给出 manifest state；只有 state 为 `ready`
且没有 finding 时，`normal_workflows_allowed` 才为 `true`。clean 单独报告，
由具体操作决定是否要求，不作为正常工作流的统一门槛。

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

全量审计遍历 manifest 的 `implementation_roots` 与全部当前事实文档，输出实现范围、
文档—`evidence` 映射、ignore 匹配、warnings 和 findings。未被 evidence 覆盖的实现
文件是 warning，不会令命令失败；结构、范围、证据与 ignorelist 错误是 finding，并以
状态码 `2` 失败。它不执行 `verification.commands`，不判断文本语义，也不写入文件。

范围审计使用精确路径清单：

```bash
python3 skills/mdf/scripts/mdf.py fact-audit --repo /path/to/repository \
  --scope paths --implementation-path src/service.py \
  --document-path docs/system/interfaces/api.md
```

### `make-id`

```bash
python3 skills/mdf/scripts/mdf.py make-id \
  --type proposal --slug service-health
```

`--type` 只能是 `proposal` 或 `bug`。`--slug` 必须为 ASCII kebab-case；命令生成
新的对象 ID，并输出相应的 `prp-...` 或 `bug-...` 标识符和 Markdown 文件名。
Proposal、Bug 与 Jot 的 ID 为类型前缀加四位字符；每一位均独立从大写英文字母
（排除 `I`、`O`）与数字 `2` 至 `9` 中等概率选择。完整形式如 `prp-A2B3`、
`bug-C4D5`、`jot-E6F7`；沟通时不得只写四位字符。
它不创建对象文件。

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

### `init`

```bash
python3 skills/mdf/scripts/mdf.py init --repo /path/to/repository \
  --latest-release 1.2.3 \
  --verification-item '{"id":"unit","kind":"unit","command":"python3 -m pytest -q"}'  \
  --implementation-root src \
  --baseline 'glossary=documented' \
  --baseline 'product_reference=documented' \
  --baseline 'system_boundary=documented' \
  --baseline 'architecture=documented' \
  --baseline 'interfaces=documented' \
  --baseline 'data=documented' \
  --baseline 'operations=documented' \
  --baseline 'deviations=documented'
```

仅接受 Git 根目录，且远端默认分支不能是 `main`。`--latest-release` 为稳定
SemVer 或 `none`。必须提供 glossary、product_reference、system_boundary、
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
`ready`。init intent 经事实复核，bootstrap intent 经起步材料核对；两者均须校验并取得
显式就绪确认，再改 ready、校验并提交。bootstrap 不调用 fact audit。
Git 化和新旧项目的语义分流由外层 intent 完成，两个 intent 共用本 CLI。

### `archive`

```bash
python3 skills/mdf/scripts/mdf.py archive --repo /path/to/repository \
  --epoch 1.2 --dry-run
```

要求 Git 根、有效 manifest、clean worktree 和零个 full-validation finding。
`--epoch` 指定一个发布切片。命令计算 Proposal/Bug 的移动，以及仓库内
canonical 链接重写。`--dry-run` 仅返回计划；正常运行会应用移动与重写，随后再次
full validate。后校验失败时保留现场，供人工检查。

### `move-change`

```bash
python3 skills/mdf/scripts/mdf.py move-change --repo /path/to/repository \
  --source /path/to/existing/change --branch-slug service-health --dry-run
```

要求 Git 根、有效 manifest 和 clean worktree。目标固定为
`docs/changes/unreleased/<branch-slug>`。未给 `--source` 时，正常运行只创建
不存在的目标目录；给出来源时，命令先验证迁移计划，再迁移目录并重写受影响的
仓库内引用。`--dry-run` 只输出目标、移动和重写计划。

### `release-closeout`

```bash
python3 skills/mdf/scripts/mdf.py release-closeout \
  --repo /path/to/repository --release-date 2026-08-04 --dry-run
```

仅接受 `release/<version>` 或 `hotfix/<version>` 当前分支；要求 Git 根、
clean worktree、`manifest.state: ready` 与 full validation 零 finding。
必须提供 `--release-date`。Core 只验证确定性审计；同次 `$mdf finish` 的语义审阅
与用户确认属于 intent 的职责。

release 会从所有 `docs/changes/unreleased/*/CHANGE.md` 汇总对象结果；hotfix 必须额外
提供 `--hotfix-change-json`。可用 `--closures-json` 覆盖或补充收口结果，
`--deferred-acceptance-json` 记录 deferred 的接受信息。正常运行会执行 manifest
声明的验证命令，保持 worktree clean 后写入版本 Change、归档对象和链接重写，并在
最后再次 full validate；`--dry-run` 不执行验证命令或写入。

### `start`

```bash
python3 skills/mdf/scripts/mdf.py start --repo /path/to/repository \
  --kind feature --name service-health \
  --proposal prp-AB23 --objectives-file /tmp/objectives.md
```

`--kind` 为 `feature`、`bugfix`、`release` 或 `hotfix`。前两者必须有 `--name`，
后两者必须有稳定 SemVer 的 `--version`。命令要求 clean worktree、`origin`、
默认分支为 `master`，且来源分支与远端完全一致；它会先 `fetch --prune`。

feature、bugfix 和 release 从 `develop` 创建，hotfix 从 `master` 创建。若新分支
在本地或远端已存在则失败。始终从基线建立相邻 worktree 并在该目录完成创建与推送，
不在当前目录开分支；成功 JSON 含该 `worktree`。成功时推送至 `origin` 并设置
upstream。
创建前检查失败不会创建分支；创建后推送失败返回 `start_push_failed`，保留本地分支，
并报告分支、来源、HEAD、`worktree`、远端状态未知与 Git 错误。调用方应先核对远端状态，
再决定补推或处理现场，不应直接重跑 `start` 或自动删除分支。

### `finish-gitflow`

```bash
python3 skills/mdf/scripts/mdf.py finish-gitflow --repo /path/to/repository
```

要求当前分支为支持的 Gitflow 交付分支、worktree clean、`origin` 存在，并要求
源和参与的目标分支都与远端完全一致。命令会先 `fetch --prune`。

feature/bugfix 以 `--no-ff --no-commit` 合并到 `develop`，再以
`chore(gitflow): 合并 <source> 到 <target>` 提交；feature 的 implemented 转换包含在该 merge commit。
release/hotfix 先同样合并到
`master`，创建带注释的 `v<version>` tag，再把 `master` 合并到 `develop`。最后
原子推送目标分支和 tag（如有）、删除远端源分支并删除本地源分支。若 `--repo` 是相邻
worktree，合并后移除该 worktree。任一 merge
冲突都会立即 abort，不会推送或删除分支。

### `upgrade`

```bash
python3 skills/mdf/scripts/mdf.py upgrade --repo /path/to/repository --dry-run
python3 skills/mdf/scripts/mdf.py upgrade --repo /path/to/repository
```

要求 Git 根，不要求 manifest、ready 或 clean worktree。默认源为
`http://10.1.5.65:8929/mars/mdf`，克隆远程默认分支 HEAD，并归档 `skills/mdf`。
`--source` 可覆盖上游。命令只替换已存在的 Agent Skills 目录中的 `mdf`，写入
`references/.version`，并更新已有 `AGENTS.md` 的唯一 MDF 托管区块；无该文件或
无区块则跳过，不新建或追加。不创建未安装位置，不覆盖 `skills/mdf`，不修改
`.mdf/` 或 `docs/`。非预览写入后仅提交本次替换路径与已更新的 `AGENTS.md`，
不夹带其他改动，不 push；无变更则不创建提交。`--dry-run` 只拉取并报告
`new_commit`、各目标当前基线、`history`、`agents` 与 `commit` 计划。`history`
按已安装 `.version` 分组，列出上游 `skills/mdf` 在该基线到 HEAD 之间的提交
与文件变更；无法对照时带 `status`，不视为失败。

## 与 intent 的关系

CLI 不负责询问用户、判定文档语义或决定交付范围。它由 intent 在完成这些判断后
调用：`init`、`bootstrap` intent 使用 `doctor`、`init` 与 `validate`；
`next` intent 优先续办在途流程，无在途时使用只读 `next` CLI 展示 PRP 蓝图；
`intake`、`bug create` 与 `prp create` 使用 `doctor` 与 `make-id`；
`jot` 使用 `make-jot-id`；
`archive` intent 使用 `archive`；`start` intent 使用 `start`；
`upgrade` intent 使用 `upgrade`；
`finish` intent 还会调用 `branch`、`move-change`、`release-closeout` 和
`finish-gitflow`。

`fact-audit`、`validate`、`semver-check` 与 `info` 提供可重复的状态、契约与版本判断。它们是
intent 和测试的确定性基础，不是面向最终用户的直接产品入口。

## Feature 阶段 CLI

feature start 额外要求 `--proposal <ID> --objectives-file <文件>`；确认的目标文本先从文件读取，
新分支记录固定起点与 slug，写入材料并提交，再推送。缺 PRP、依赖阻塞或已开工时拒绝。

`delivery <action> --repo <仓库>`：

| action | 输入与效果 |
| --- | --- |
| status | 只读列出交付身份、材料位置与阶段记录 |
| check | `--stage` 指定待进入阶段或 finish，检查前置和证据有效性 |
| record | `--stage` 与非空 `--summary`，写入通过 CLI 检查的语义审查记录 |
| verify | 执行全部 verification；可用重复 `--item <id>` 做定位运行，全量记录不能由单项替代 |
| worktree | `--role qa` 或 `dev`；从已提交 design 基线建立或复用对应本地分支与相邻 worktree |
| integrate | clean feature 依次 no-ff 集成已有 qa/dev；冲突保留现场，完成后清理已合并本地工作分支 |

design record 需要 `--policy-file <JSON>`，格式为 `{"protected_paths":["tests/","pyproject.toml"]}`。
converge/integrate 的测试规则变更需要 `--test-approval <用户确认记录>`；该文本是授权证据，不是自动授权。
阶段值为 design、write-tests、implement、converge、review、fact-update。

`next` CLI 不识别或推进 workflow；在途判断与原流程委托由 next intent 完成。
`next --repo <仓库> [--depth 3]` 输出 trees、blocked、needs_review、hidden；只读，非法依赖失败。
`prp-split --repo <仓库> --spec-file <JSON> [--dry-run]` 在完整预检后一次写入拆分结果。
输入包含 source、children、downstream、rationale；children 每项含 filename、id、depends_on、body，
downstream 是全部原下游 ID 到所需子 ID 列表的映射。预览输出候选文件全文，失败不留下部分拆分。
子 PRP 继承原 PRP 的可选 `milestone`；原 PRP 未声明时省略该字段，不写 `null`。
