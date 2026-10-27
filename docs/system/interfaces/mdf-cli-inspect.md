# MDF CLI：只读命令

调用约定与命令总表见 [MDF 确定性 CLI 参考](mdf-cli.md)。


## `info`

```bash
python3 skills/mdf/scripts/mdf.py info
```

输出 `tool_version`、`protocol_version` 和 `schema_version`。当前三者都必须为
数字 `3`；intent 以此拒绝错误或不兼容的 CLI。

## `project-rules`

```bash
python3 skills/mdf/scripts/mdf.py project-rules --repo /path/to/repository --stage design
```

只读加载 manifest 中所选阶段的 rule，不执行文件；`--stage` 必填，只接受 design 或 code-review。

- 要求 Git 根和 manifest，不额外要求 ready 或 clean。
- 输出 `stage`、`project_rule`；未配置为 null，否则含 `path`、完整 `content` 与 `sha256`。
- 配置或文件无效时以 `invalid_rules` 非零退出；doctor / validate 同类 finding 为 `manifest.rules`。
- 配置、文件约束和 Agent merge 契约见
  [项目阶段 rule 契约](../../../skills/mdf/references/project-rules.md)。

## `doctor`

```bash
python3 skills/mdf/scripts/mdf.py doctor --repo /path/to/repository
```

报告目标路径的仓库状态：

- Git 根、是否为 Git 根、worktree 是否 clean，及当前分支的解析结果。
- `.mdf/manifest.yaml` 是否存在和 manifest 校验 findings。
- 已初始化仓库会给出 manifest state。
  - state 为 `ready` 且没有阻断性 finding 时，`normal_workflows_allowed` 为 `true`。
  - `evidence.stale`、`generated.stale` 仍完整报告，但不阻断正常工作流。
  - warning 仅报告，不阻断任何工作；其他 error 仍阻断；`validate full` 与 fact audit 仍因 stale 失败。
- 进行中的 `changes/unreleased/<slug>/` 只要有 `delivery.json`，缺少 CHANGE.md 不构成 finding。
- clean 单独报告，由具体操作决定是否要求，不作为正常工作流的统一门槛。

| 条件 | finding |
| --- | --- |
| `schema_version` 不是当前值 | `manifest.schema` |
| `docs/product/` 或 `docs/adr/` 目录、根 `docs/testing.md` 存在 | `layout.migrate` |
| 缺少 `docs/system/testing/index.md` 或其主题叶 | `layout.testing` |

schema 与 `layout.migrate` 指向 `$mdf migrate`。

stderr 依次报告仓库识别、MDF 契约检查与状态汇总；契约检查细分为配置与布局、
工作对象、链接与记录、发布历史、事实与 evidence。未初始化时只检查布局。

事实与 evidence 阶段先报告文档扫描，再逐项报告已检查数量、总数、当前路径与用时。
文档与每页 evidence 分别计数；当前项完成后才增加已检查数。
generated 另报告 source、generator 及其 Git history 检查位置。

## `validate`

```bash
python3 skills/mdf/scripts/mdf.py validate --repo /path/to/repository \
  --level basic
```

`--level` 可为 `basic`（默认）或 `strict`。两者扫描相同的 MDF 管理范围；
`strict` 额外检查 evidence 与 generated 的 Git 跟踪、脏状态和提交先后。
`basic` 仍检查配置、布局、记录、事实页格式与 evidence 路径。
JSON 结果用 `level` 返回校验级别；不接受文件路径列表。
存在 finding 时仍输出完整 JSON 结果；仅有 warning 时成功，
存在 error 时以状态码 `2` 失败。

stderr 报告 scope 与契约检查阶段；检查结束不代表没有 finding。

## `fact-audit`

```bash
python3 skills/mdf/scripts/mdf.py fact-audit --repo /path/to/repository
```

`--scope` 可为 `full`（默认）、`branch` 或 `paths`。

`--quick` 为独立 freshness 检查，可与 scope/base/paths 按原参数规则组合，不与 against 混用。

- 只校验范围内 evidence 与 generated 的有效性、Git tracked、dirty 和提交先后。
- 不运行全量契约、文档结构或覆盖检查；不调用 Agent、tests 或 generator。
- branch 包含删除、目录 evidence 与 generated 依赖；paths 自动纳入指定实现影响页。
- shallow checkout 报 `audit.shallow`，不自动 fetch；CI 应准备完整 history。
- 输出 `mode: quick`、`semantic_review: false`、`document_paths`、`ignored` 与 findings。
  - `ignored` 是被排除事实页的路径列表；完整 audit 的原 payload 不变。
  - 无 finding 返回 0，有 finding 返回 2；参数、配置与执行异常同样非零。
- quick 通过只表示未发现 stale 或证据有效性问题，不替代主链完整 fact audit。

全量审计遍历 module `sourceset` 并集中的已跟踪实现文件与全部当前事实文档。
未归属实现不进入语义审阅或覆盖检查；文档按自身契约独立纳入。

stderr 依次报告全量契约校验、范围解析、文档结构检查、evidence 与覆盖映射；
范围解析后报告 scope、实现文件数与事实文档数。

- 输出实现范围、文档—`evidence` 映射、ignore 匹配、warnings 和 findings。
- 未被 evidence 覆盖的实现文件是 warning，不会令命令失败。
- 结构、范围、证据与 ignorelist 错误是 finding，并以状态码 `2` 失败。
- 它不执行 manifest `verification`，不判断文本语义，也不写入文件。

它同时按文档角色检查体积（物理行；`AGENTS.md` 的 `size.hard` 只计托管区块），
超出为 `size.hard` finding：

| 文档 | 行数上限 |
| --- | --- |
| 路由页（`docs/README.md`、`docs/user-guide/README.md`、`docs/system/overview.md`、切面 `index.md`） | 100 |
| `AGENTS.md` 托管块与 `PROJECT.md` | 100 |
| 根 `README.md` | 200 |
| `docs/user-guide/`、`docs/system/` 主题叶 | 450 |
| `docs/context/adr/` | 300 |
| Bug | 500 |
| Proposal、`docs/JOTS.md` | 不限 |

- module `ignore` 仅匹配自身 `sourceset`，可排除源代码、测试源代码与文档。
  - 重叠归属时，其他未忽略该文件的 module 仍保留验证与检查。
  - 命中后跳过 `code.size`、`size.hard` 与 `prose.*`，免除长度与 70% 拆分要求。
  - `ignored` 返回命中路径、`ignore_path` 与 `reason`；未匹配文件仍正常检查。
- 未排除文件超限必须拆分，每个结果不超过对应硬限制的 70%，整数向下取整；审查复核拆分结果。
- 源代码与测试源代码单文件默认超过 1000 行报 `code.size`，默认拆分后每个最多 700 行。
  - module `size_limits` 可 override 行数、package 文件数及拆分比例；缺省字段为 1000/50/70。
  - 同一对象满足全部适用 module 配置，finding 标明触发 module、硬上限及其拆分目标。
  - `full` 检查全仓已跟踪代码；`branch` 检查改动代码；`paths` 检查指定实现路径中的代码。
  - 扩展名集合见 `mdf_core/inspection/code_size.py`；配置、数据、文档与 lockfile 不计。
- package 对目录直属实现、测试源文件分别计数；默认超过 50 报 `package.size`，默认拆分后每类最多 35。
  - 始终统计完整同类成员总数，按成员匹配的全部 module 配置检查；有未归属成员时默认策略也参与。
  - 文档角色上限、70% 拆分要求及 `prose.*` 不受 module `size_limits` 影响。
  - 子目录独立计数；`__init__.py` 计入，配置、数据、文档与 ignore 命中文件不计。
  - full 检查全部 package；branch/paths 检查触及 package 的全部现存成员，含未改动文件。
  - 测试命名规则见 `mdf_core/inspection/code_size.py`，同目录的实现与测试也不相加。
- Proposal、`docs/JOTS.md` 与 HTML 不检查行数上限；Proposal 的正文仍执行结构检查。
- `AGENTS.md` 只检查 MDF 托管块，不对整份文件另设行数 warning。
- `full` 检查全部带角色文档；`branch`、`paths` 只检查范围内文档与本次改动到的入口页。

同一检查面还按 `skills/mdf/references/doc-structure.md` 报结构硬限制（`docs/JOTS.md` 除外，
`AGENTS.md` 只查托管区块）：

| code | 触发条件 |
| --- | --- |
| `prose.block` | 连续散文超过 6 行 |
| `prose.sentence` | 单句显示宽度超过 200（中文算 2 个） |
| `prose.list_item` | 单个列表项超过 4 行 |
| `prose.section` | 一个标题下散文合计超过 15 行 |
| `prose.emoji` | 出现 ⚠️ ✅ ❌ 💡 📌 📂 📍 ⬇️ 以外的 emoji |

分支范围审计以 `--base` 指定起点 commit（省略时取 `merge-base develop HEAD`）。

- 实现范围是起点以来改动的实现文件。
- 文档范围是改动到的事实页与 evidence 引用这些实现的事实页。
- 结果含 `base`。
- `--base` 可以是 commit 或 tag；close-out release 传入上一正式发布：

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

### 当前工作区对比事实审阅

```bash
python3 -B skills/mdf/scripts/mdf.py fact-audit --repo /path/to/repository \
  --against <ref>
python3 -B skills/mdf/scripts/mdf.py fact-audit-report-check \
  --context-file /outside/context.json --report-file /outside/report.json
```

- against 不与 scope/base/paths 混用；普通 CLI 默认 full 不变。
- 直接比较指定历史版本与当前工作区，含 staged、unstaged 和非忽略 untracked 文件。
- 仓外 snapshot 不修改原仓库 HEAD、index 或 objects；不运行项目 hooks、filters 或 tests。
- rules、sourceset、module ignore 均来自当前工作区；未归属实现不进入语义审阅。
- 当前 snapshot 的契约问题仍保留 findings；未提交内容不冒充已验证事实。
- 返回 `ok: true, result: context` 只表示 context 构建成功，不表示语义审阅通过。
- context 包含 against、worktree_sha256、diff、双侧事实映射、范围、确定性 audit 与指纹。
- report-check 验证指纹、覆盖、warning 处置和结论；格式正确不证明语义判断正确。
- 日志与 JSON report 均保存在 checkout 外。
- Agent 执行与 report 契约见 [独立事实审阅](../../../skills/mdf/references/fact-audit-against.md)。

## `prose-check`

```bash
python3 skills/mdf/scripts/mdf.py prose-check --repo /path/to/repository [--path docs/a.md ...]
```

按 `skills/mdf/references/doc-structure.md` 列出结构硬限制违例，供 `$mdf prettify` 使用。

- 省略 `--path` 时检查全部带角色文档（`docs/JOTS.md` 除外）；`--path` 可重复，
  接受任意仓库内 Markdown。
- `AGENTS.md` 只查托管区块；不要求 manifest ready。
- 存在 `.mdf/modules.yaml` 时遵守 module `ignore` 的适用范围，显式 `--path` 同样生效；`ignored` 列出排除路径。
- 输出 `checked`（不含排除文件）、`issue_count` 与逐条 `issues`（`path`、`line`、`code`、`message`）；
  有违例时以状态码 `2` 退出。

## `list`

```bash
python3 skills/mdf/scripts/mdf.py list --repo /path/to/repository \
  --type bug --status open
python3 skills/mdf/scripts/mdf.py list --repo /path/to/repository \
  --type proposal --status draft --status ready --milestone 阶段一
```

只读列出 `docs/proposals/` 与 `docs/bugs/` 顶层的 active 对象，不含 `archive/`。
要求 Git 根与 manifest 存在，不要求 `ready` 或 clean。

- `--type` 为 `proposal` 或 `bug`，省略时两者都列。
- `--status` 可重复，须是所选类型的合法状态。
- `--milestone` 只适用于 Proposal，`--severity` 只适用于 Bug，两者不能同时使用。
  - 与 `--type` 冲突时以 `invalid_filter` 失败。

每条 `objects` 含 `id`、`type`、`status`、`title`（正文首个一级标题）与 `path`。

- Proposal 额外给出：
  - `depends_on`。
  - `blocked_by`（未满足的直接依赖，含归档 Proposal 的状态判断）。
  - `in_progress`（当前工作区或任一 feature 分支存在该 PRP 的开工记录）。
  - `milestone`。
- Bug 额外给出 `severity`、`found_in`、`fixed_in`、`reject-reason` 与 `duplicate_of`。
- 缺失字段为 `null`。
- frontmatter 损坏、文件名不合规或缺少 `id`/`status` 的 active 文件不使命令失败。
  - 而是列入 `skipped` 并附原因；契约校验仍由 `validate` 负责。

## `make-id`

```bash
python3 skills/mdf/scripts/mdf.py make-id \
  --type proposal --repo /path/to/repo --slug service-health
```

命令生成新的对象 ID，并输出相应的 `prp-...` 或 `bug-...` 标识符和 Markdown 文件名。
它不创建对象文件，也不检查仓库内 slug 是否唯一。

- `--type` 只能是 `proposal` 或 `bug`。
- `--slug` 必须为 ASCII kebab-case，且不得与对象 ID 同形。
- 新生成的 Proposal ID 为 `prp-` 加四位随机字符，前两位为数字，后两位最多一个字母（排除 `I`、`O`）。
  - `make-id --type proposal` 必须提供 `--repo`。
  - 数字允许 `0` 至 `9`；在 `planning` 上生成，避开 active、archive 及本批已有 ID。
  - 只读生成、不预占 ID；跨 checkout 的重复由合入后的唯一性校验发现。
- 已有数字 Proposal ID 继续有效，校验、引用与文件名无需改写。
- Bug 与 Jot 仍为类型前缀加四位字符。
  - 每一位从大写英文字母（排除 `I`、`O`）与数字 `0` 至 `9` 中选择。
  - 新生成的四位字符至少包含一个字母和一个数字。
- 完整形式如 `prp-0001`、`bug-C4D5`、`jot-E6F7`。
  - ❌ 沟通时不得省略前缀或只写序号/短码。

## `make-jot-id`

```bash
python3 skills/mdf/scripts/mdf.py make-jot-id
```

生成一个 `jot-...` 标识符，供 `$mdf jot` 在 `docs/JOTS.md` 中定位原始记录。它不创建或
修改文件。

## `branch`

```bash
python3 skills/mdf/scripts/mdf.py branch --name feature/service-health
```

以 `--name` 解析分支；未提供时从 `--repo` 的当前分支读取。它会输出是否为
支持的 Gitflow 分支，以及分支类型、slug 或版本等结构化详情。两者均未提供时失败。

## `semver-check`

```bash
python3 skills/mdf/scripts/mdf.py semver-check \
  --previous 1.2.3 --candidate 1.3.0 --categories Added,Fixed
```

比较两个稳定 `MAJOR.MINOR.PATCH` 版本。`--categories` 可包含 `Added`、
`Changed`、`Deprecated`、`Removed`、`Fixed`、`Security`，或独占的 `none`；
`--breaking` 声明破坏性变更。命令输出实际与要求的 bump 类型；候选版本不足，
或 `Removed` 未声明 `--breaking` 时以状态码 `2` 失败。

- 上一版与候选都低于 `1.0.0` 时，第二位的变化是 major，第三位的变化是 minor。
- 从 `0.x` 升到 `1.0.0` 仍是 major。

## `run`

```bash
python3 skills/mdf/scripts/mdf.py run --repo /path [--name pytest] -- \
  python3 -m pytest tests/lint
```

代跑任意命令并落盘，供 Agent 代替 tee。

- 只要求 `--repo` 是目录；不要求 Git 根、manifest 或 clean worktree。
- 子进程原文写到终端 stderr；结果 JSON 在 stdout。
- 日志目录为 `.mdf/logs/<时间戳>-<名称>/`；无 `.mdf/` 时见调用约定。
- 设置 `MDF_REPORT_DIR` 与 `NO_COLOR=1`。pytest 等应把 JUnit 写进该目录。
- `--name` 默认 `run`，只用于日志目录名。
- 子进程非 0 时失败，details 含 `exit_code`、`log`、`command`。
