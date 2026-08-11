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
  clean worktree。
- 写入类命令不会创建 Git commit；调用方必须展示结果，并由用户复核、提交。
- `--dry-run` 只在 `archive`、`move-change` 和 `release-closeout` 中有效。

## 命令表

| 命令 | 类别 |
| --- | --- |
| `info` | 版本信息 |
| `doctor` | 仓库状态 |
| `init` | 初始化写入 |
| `validate` | 确定性校验 |
| `make-id` | 对象 ID |
| `make-jot-id` | Jot ID |
| `branch` | 分支解析 |
| `semver-check` | 版本校验 |
| `archive` | 对象归档 |
| `move-change` | Change 迁移 |
| `release-closeout` | 版本收口 |
| `start` | 创建分支 |
| `finish-gitflow` | Gitflow 合并 |

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
已初始化仓库会给出 manifest state；只有 state 为 `ready`、worktree clean
且没有 finding 时，`normal_workflows_allowed` 才为 `true`。

### `validate`

```bash
python3 skills/mdf/scripts/mdf.py validate --repo /path/to/repository \
  --scope targeted
```

`--scope` 可为 `targeted`（默认）或 `full`。两者都校验 MDF 确定性契约；
`full` 额外执行全量检查。存在 finding 时仍输出完整 JSON 结果，
但以状态码 `2` 失败。

### `make-id`

```bash
python3 skills/mdf/scripts/mdf.py make-id \
  --type proposal --slug service-health
```

`--type` 只能是 `proposal` 或 `bug`。`--slug` 必须为 ASCII kebab-case；命令生成
新的 ULID，并输出相应的 `prp-...` 或 `bug-...` 标识符和 Markdown 文件名。
它不创建对象文件。

### `make-jot-id`

```bash
python3 skills/mdf/scripts/mdf.py make-jot-id
```

生成一个 `jot-...` 标识符，供 `$mdf jot` 在 `JOTS.md` 中定位原始记录。它不创建或
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
  --verification-command "python3 -m pytest -q" \
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
每项格式为 `NAME=documented[:仓库相对路径]` 或
`NAME=not_applicable:原因`。
至少提供一次 `--verification-command`；可重复提供。没有业务检查的空仓库可使用
`git diff --check`。

它创建或更新 MDF 固定 scaffold，包括 `.mdf/manifest.yaml`、托管的
`AGENTS.md` 区块和文档骨架。输出会列出拟创建或更新的文件和 diff；实际写入后
manifest 保持 `initializing`，但会写入提供的 verification commands，不会切换到
`ready`。intent 必须在事实复核与显式就绪确认后完成后续校验。

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
`changes/unreleased/<branch-slug>`。未给 `--source` 时，正常运行只创建
不存在的目标目录；给出来源时，命令先验证迁移计划，再迁移目录并重写受影响的
仓库内引用。`--dry-run` 只输出目标、移动和重写计划。

### `release-closeout`

```bash
python3 skills/mdf/scripts/mdf.py release-closeout \
  --repo /path/to/repository --release-date 2026-08-04 \
  --semantic-attestation-json \
  '{"semantic":"passed","finding_count":0,"summary":"已完成审阅"}' \
  --dry-run
```

仅接受 `release/<version>` 或 `hotfix/<version>` 当前分支；要求 Git 根、
clean worktree、`manifest.state: ready` 与 full validation 零 finding。
必须提供 `--release-date` 和不含 `waivers` 的语义 attestation JSON，其中
`semantic` 为 `passed`、`finding_count` 为 `0`，并有非空 `summary`。

release 会从所有 `changes/unreleased/*/CHANGE.md` 汇总对象结果；hotfix 必须额外
提供 `--hotfix-change-json`。可用 `--closures-json` 覆盖或补充收口结果，
`--deferred-acceptance-json` 记录 deferred 的接受信息。正常运行会执行 manifest
声明的验证命令，保持 worktree clean 后写入版本 Change、归档对象和链接重写，并在
最后再次 full validate；`--dry-run` 不执行验证命令或写入。

### `start`

```bash
python3 skills/mdf/scripts/mdf.py start --repo /path/to/repository \
  --kind feature --name service-health
```

`--kind` 为 `feature`、`bugfix`、`release` 或 `hotfix`。前两者必须有 `--name`，
后两者必须有稳定 SemVer 的 `--version`。命令要求 clean worktree、`origin`、
默认分支为 `master`，且来源分支与远端完全一致；它会先 `fetch --prune`。

feature、bugfix 和 release 从 `develop` 创建，hotfix 从 `master` 创建。若新分支
在本地或远端已存在则失败；成功时创建分支、推送至 `origin` 并设置 upstream。

### `finish-gitflow`

```bash
python3 skills/mdf/scripts/mdf.py finish-gitflow --repo /path/to/repository
```

要求当前分支为支持的 Gitflow 交付分支、worktree clean、`origin` 存在，并要求
源和参与的目标分支都与远端完全一致。命令会先 `fetch --prune`。

feature/bugfix 以 `--no-ff --no-commit` 合并到 `develop`，再以
`chore(gitflow): 合并 <source> 到 <target>` 提交。release/hotfix 先同样合并到
`master`，创建带注释的 `v<version>` tag，再把 `master` 合并到 `develop`。最后
原子推送目标分支和 tag（如有）、删除远端源分支并删除本地源分支。任一 merge
冲突都会立即 abort，不会推送或删除分支。

## 与 intent 的关系

CLI 不负责询问用户、判定文档语义或决定交付范围。它由 intent 在完成这些判断后
调用：`init` intent 使用 `doctor` 与 `init`；`doc create` 使用 `make-id`；
`jot` 使用 `make-jot-id`；
`doc archive` intent 使用 `archive`；`start` intent 使用 `start`；
`finish` intent 还会调用 `branch`、`move-change`、`release-closeout` 和
`finish-gitflow`。

`validate`、`semver-check` 与 `info` 提供可重复的状态、契约与版本判断。它们是
intent 和测试的确定性基础，不是面向最终用户的直接产品入口。
