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
- 配置或文件无效时以 `invalid_rules` 非零退出；`check --profile entry` 与 IG strict 同类 finding 为 `manifest.rules`。
- 配置、文件约束和 Agent merge 契约见
  [项目阶段 rule 契约](../../../skills/mdf/references/project-rules.md)。

## `check`

```bash
python3 skills/mdf/scripts/mdf.py check --repo /path/to/repository --profile entry
python3 skills/mdf/scripts/mdf.py check --repo /path/to/repository --profile dev --scope branch
```

| Profile | Scope | 检查 |
| --- | --- | --- |
| `entry` | 省略 | Git 身份、manifest、modules、布局、Agent 控制面 |
| `objects` | full（默认）、paths | 全局对象与引用约束；paths 复验显式 PRP、Bug 的结构 |
| `dev`（默认） | branch（默认）、full、paths | 影响集链接、anchors、文档结构、evidence、覆盖 |
| `closeout` | branch（默认）、full、paths | 全局对象约束与影响集机械规则，含 Git freshness |

- branch 接受 `--base <commit>`；可用 `--against <commit>`，互斥 scope、base 与路径。
- paths 至少传一个路径。可重复传 `--document-path`；dev、closeout 也接受 `--implementation-path`。
- `--only` 仅供 dev，逗号分隔 `contract,links,size,prose,overview,evidence`。
- 每条 finding 保留 `severity` 并提供 `disposition`。覆盖提示和本地产物 symlink 为 advisory。
- JSON 的 `executed_checks` 与 `skipped_checks` 列出检查组。
- entry 允许未初始化目录；采集成功退出 0，准入看 `normal_workflows_allowed`。
- 其余 Profile 有 blocking finding 退出 2，无阻断退出 0；参数或执行错误退出 1。
- 运行期间保持工作区稳定。entry、objects、dev 跳过 Git freshness。
- 删除路径仍触发影响页和引用检查，但不进入 `implementation_paths` 或产生 `audit.uncovered`。
- 非 entry 的契约检查与 `fact-audit` 共用 `audit.ignore_empty`。
  - full、paths 的 ignore 规则须命中当前已跟踪文件。
  - branch、against 按基线与当前候选路径并集匹配，当前候选包含未跟踪文件；删除仍可命中基线。
- 非 UTF-8 事实页以 `fact.frontmatter` 报错；文档体积与结构检查以 `document.encoding` 报错，退出 2。

## `validate --level strict`

```bash
python3 skills/mdf/scripts/mdf.py validate --repo /path/to/repository --level strict
```

IG 的全库契约检查。显式 `--level strict` 必填；退出码按固有 `severity` 判定，有 error 返回 2。
冻结规则包含 evidence freshness，链接只检查目标是否存在。文档体裁、散文与覆盖规则由 `check` 和 `fact-audit` 检查。

## `fact-audit`

```bash
python3 skills/mdf/scripts/mdf.py fact-audit --repo /path/to/repository
```

`--scope` 可为 `full`（默认）、`branch` 或 `paths`。

`--quick` 仅与 `--against <commit>` 组合，跳过 LLM，保留快照及机械检查。
不强制 clean；`--scope branch` 经 resolve-base 后等同 against。

- 复用完整 audit 的确定性检查：契约、文档结构、evidence / generated 的有效性、Git tracked、提交先后与 must-cover uncovered。
- 不调用 Agent 或 generator；不替代主链完整 fact audit。
- branch/against 包含删除、目录 evidence 与 generated 依赖；paths 自动纳入指定实现影响页。
- shallow checkout 报 `audit.shallow`，不自动 fetch；CI 应准备完整 history。
- against/branch：`mode`/`semantic_review` + `result` context；非 quick 的 exit 0 只表示 context 成功。
- 所有 quick：无 finding/warning 返回 0；存在 finding 或未处置 warning（含 uncovered）返回 2。

全量审计遍历 module `sourceset` 并集中的已跟踪实现文件与全部当前事实文档。
未归属实现不进入语义审阅或覆盖检查；文档按自身契约独立纳入。

stderr 依次报告全量契约校验、范围解析、文档结构检查、evidence 与覆盖映射；
范围解析后报告 scope、实现文件数与事实文档数。

- 普通 CLI 输出 manifest `state`、实现范围、文档—`evidence` 映射、ignore 匹配、warnings 和 findings。
  - direct intent 在语义审阅前要求 `state: ready`；CLI 保留 `initializing` 结果供 migrate 使用。
  - quick 与 against 不增加此字段或 ready 前置。
- 未被 evidence 覆盖的实现文件是 warning，不会令命令失败。
- 结构、范围、证据与 ignorelist 错误是 finding；存在 `severity: error` 时以状态码 `2` 失败。
  - 仅有 warning 时 CLI 成功；完整 Agent audit 仍须逐条处置全部 warning。
- 它不执行 manifest `verification`，不判断文本语义，也不写入文件。

它同时按文档角色检查体积（物理行；`AGENTS.md` 的 `size.hard` 只计托管区块），
超出为 `size.hard` finding：

| 文档 | 行数上限 |
| --- | --- |
| 路由页（`docs/README.md`、`docs/user-guide/README.md`、`docs/system/overview.md`、切面 `index.md`） | 100 |
| `AGENTS.md` 托管块与 `PROJECT.md` | 100 |
| 根 `README.md` | 200 |
| `docs/user-guide/`、`docs/system/` 主题叶 | 450，合格 `doc_style: reference` 为 1200 |
| `docs/context/adr/` | 300 |
| Bug | 500 |
| Proposal、`docs/JOTS.md` | 不限 |

- module `ignore` 仅匹配自身 `sourceset`，可排除源代码、测试源代码与文档。
  - 重叠归属时，其他未忽略该文件的 module 仍保留验证与检查。
  - 命中后跳过 `size.hard` 与 `prose.*`，免除长度与 70% 拆分要求。
  - `ignored` 返回命中路径、`ignore_path` 与 `reason`；未匹配文件仍正常检查。
- 未排除文件超限必须拆分，每个结果不超过对应硬限制的 70%，整数向下取整；审查复核拆分结果。
- 代码行数与 package 文件数由 [统一 lint](../../../skills/mdf/references/lint.md) 检查。
  - fact audit 不产生 `code.size` 或 `package.size`。
  - 文档角色上限、70% 拆分要求及 `prose.*` 不受 module `size_limits` 影响。
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

- 分支范围以 `--base` 指定起点。省略时，release 用上一发布 tag，其他交付用 `delivery.start_commit` 或 Git config。
- 无账本 adhoc 用固定范围。普通 fallback 取 integration 分支与 HEAD 的 merge-base，gitflow 用 develop，github-flow 用 trunk。
- 非 quick 的 branch 审阅使用 `clear_commit`，仅 clean 且无相关变化时返回 `skip_audit: true`。显式 against 采用固定基线。
- 整仓语义审阅通过后，owner 可执行 `fact-audit-record-full --repo <repo> --head <SHA>` 记录实际审阅的 clean commit。

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

### against → HEAD 事实审阅

```bash
python3 -B skills/mdf/scripts/mdf.py fact-audit --repo /path/to/repository \
  --against <ref>
python3 -B skills/mdf/scripts/mdf.py fact-audit --repo /path/to/repository \
  --against <ref> --quick
python3 -B skills/mdf/scripts/mdf.py fact-audit-report-check \
  --repo /path/to/repository --context-file /outside/context.json --report-file /outside/report.json
```

- against 不与 scope/base/paths 混用；右端点为当前工作区（可 dirty）。
- 仓外 snapshot 不修改原仓库；不运行 hooks、filters 或 tests。
- rules、sourceset、module ignore 来自当前工作区；未归属实现不进入语义审阅。
- 非 quick 返回 `ok: true, result: context` 只表示 context 成功；quick 的 `ok` 与退出码反映机械结论，`semantic_review: false`。
- context 含 against、worktree_sha256（工作区树指纹）、diff、映射、audit 与指纹。
- report-check 验证指纹与覆盖；工作区或 HEAD 身份变化须重建 context。
- Agent 契约见 [旁路与报告](../../../skills/mdf/references/fact-audit-against.md)；
  交付外壳见 [交付事实审阅](../../../skills/mdf/references/fact-audit-delivery.md)。

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
  - 而是列入 `skipped` 并附原因；契约校验由 `check` 负责。

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
- 日志目录为 `.mdf/logs/<时间戳>-<名称>/`；无 `.mdf/` 或不可写时见调用约定。
- 设置 `MDF_REPORT_DIR` 与 `NO_COLOR=1`。pytest 等应把 JUnit 写进该目录。
- `--name` 默认 `run`，只用于日志目录名。
- 子进程非 0 时失败，details 含 `exit_code`、`log`、`command`。
