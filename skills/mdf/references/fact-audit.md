# Fact Audit

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve scope                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Audit CLI                      │
└────────────────┬─────────────────┘
                 │
                 ├──── 无法审阅 ────→ [停止]
                 │
                 ▼ 可审阅
┌──────────────────────────────────┐
│ 3 Review facts                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 无法完成复核 ────→ [停止]
                 │
                 ▼ 通过（含已记录发现）
┌──────────────────────────────────┐
│ 4 Review coverage                │
└────────────────┬─────────────────┘
                 │
                 ├──── 无法完成复核 ────→ [停止]
                 │
                 ▼ 通过（含已记录发现）
┌──────────────────────────────────┐
│ 5 Review warnings                │
└────────────────┬─────────────────┘
                 │
                 ├──── 无法完成审阅 ────→ [停止]
                 │
                 ▼ 通过（含未确认项记录）
┌──────────────────────────────────┐
│ 6 Validate                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败且独立调用 ────→ [停止]
                 ├──── 失败且内部委托 ────→ [返回未通过，调用方走失败分支]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 7 Confirm review                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ────────────────→ [审阅通过]
                 ├──── 未通过且独立调用 ────→ [报告未通过并结束]
                 └──── 未通过且内部委托 ────→ [返回未通过，调用方走失败分支]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/common.md` 与 `references/repository-contract.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve scope | 约束 | 确认调用方、状态与 `--scope`（branch/full/paths） | 类型、scope、范围、state | 2 | 停止 |
| 2 | Audit CLI | 脚本 | 按 scope 运行 fact-audit CLI | 映射、体积、表与入口、findings | 可审阅→3 | 无法审阅则停止 |
| 3 | Review facts | 约束 | 逐份核对事实与 evidence，并审阅结构 | 事实复核、语义发现、warning | 4 | 无法复核则停止 |
| 4 | Review coverage | 约束 | 从实现反查用户与系统各面的文档覆盖 | 覆盖、遗漏与错误 | 5 | 无法复核则停止 |
| 5 | Review warnings | 约束 | 逐条审阅 CLI 与步骤 3 的 warning | 逐条处置 | 6 | 无法审阅则停止 |
| 6 | Validate | 脚本 | 运行 full validation，不跑验证命令 | validation findings | 7 | 独立停止；委托返回未通过 |
| 7 | Confirm review | 约束 | 报告发现并取得当场确认 | 摘要、当场确认 | 审阅通过 | 报告未通过；独立结束，委托返回 |

## 术语与数据结构

### 范围与确定性映射

<a id="s1"></a>

#### 范围

除委托确认记录外只读：本流程不写入、移动、提交、生成持久报告；
不执行 `.mdf/modules.yaml` 验证入口，也不调用 `$mdf verify`。
步骤 7 的确认记录由调用方写入并提交。

`--scope` 三选一，与 fact update 共用；列出 `<path>...` 即 `paths`，
与 `--scope full` 或 `--scope branch` 同用时停止询问：

- `branch`：独立调用默认。
  - 交付分支以 `delivery.json` 的 `start_commit` 为 `--base`。
  - 没有时取 git config `branch.<owner 分支>.mdf-start-commit`。
  - 都没有才由 CLI 取 `merge-base develop HEAD`。
  - 主链 release（verify full 之后、close-out 之前）传入上一正式发布为 `--base`。
  - 范围是该起点以来改动的实现文件、改动到的事实页，以及 evidence
    引用这些实现的事实页；同时检查改动到的入口页体积。
- `full`：全部当前事实、实现面、入口根文档、ADR 与工作对象体积。
- `paths`：调用方或独立调用给出精确实现/文档路径；未给路径时停止询问。

确定类型和状态：

| 调用方 | 范围与状态 |
| --- | --- |
| fact update 委托 | 与 fact update 相同的 `--scope`、`--base` 与路径，允许审阅调用方的同次写入 |
| direct 调用 | 步骤 1 运行 `doctor --repo "$REPO_ROOT"` 读取 state，非 `ready` 即停止 |
| migrate | `full`，允许 `initializing` |
| 已收口 release/hotfix（直接委托） | `branch`（`--base` 为上一正式发布）或等价 `paths`，不得改用 `full` |
| 主链其他（含待收口 release） | 经 fact update 委托或直接 audit，`--scope` 同调用方，不得改用 `full` |

首次发布无上一版本时停止确认初始基线。
审阅不要求 clean，不替调用方提交；未提交内容仍须满足 evidence 与 full validation 契约。

验收：调用方、scope 与范围。

<a id="s2"></a>

#### 映射

按 scope 运行下列命令之一，必须显式传 `--scope`，不得省略：

```bash
python3 "$MDF_ROOT/scripts/mdf.py" fact-audit --repo "$REPO_ROOT" --scope full
python3 "$MDF_ROOT/scripts/mdf.py" fact-audit --repo "$REPO_ROOT" --scope branch [--base <base>]
python3 "$MDF_ROOT/scripts/mdf.py" fact-audit --repo "$REPO_ROOT" --scope paths \
  [--implementation-path <实现路径>]... [--document-path <文档路径>]...
```

- 独立调用省略时传 `--scope branch`。裸 CLI 省略时仍为 `full`，本流程不使用该默认。
- `branch` 的 `--base` 按上方范围规则传入；省略时 CLI 取 `merge-base develop HEAD`。
- `paths` 每个路径一个参数，至少一个：当前事实文档传 `--document-path`，实现根下已跟踪文件传
  `--implementation-path`；两者都不是时停止询问。`full` 不带路径与 `--base`。
- CLI 按 `repository-contract.md` 的体积表检查 `size.hard`。
- 范围内的 `docs/system/overview.md` 由 CLI 检查核心模块表，
  不合则 `overview.core_modules` finding：
  - 五行必须是配置、可观测性、错误、鉴权、限制与恢复。
  - 每行「打开」列为主题叶链接或「不适用：」加一句理由。
- 范围内的 `PROJECT.md` 须含下列入口，缺则 `project.entry_links` finding：
  - `docs/system/overview.md`、`docs/README.md` 与 `docs/system/testing/index.md`。

验收：范围、文档—`evidence` 映射、ignore 匹配、体积、核心模块表、入口指向、warnings、findings。

通过条件：得到可解析 payload；findings 非空时 CLI 退出码为 2，仍按 payload 处理。

- `size.hard`、`overview.core_modules`、`project.entry_links` 不在本步停止。
- migrate 仅 `manifest.initializing` 也继续。

异常与交接：出现以下任一情况时停止。

- 无结构化输出。
- findings 含下列任一 code：
  - `audit.scope`、`audit.base`、`audit.scope_path`。
  - `modules.invalid`、`modules.missing`。

不得把解析失败当作初始化豁免。

### 双向复核与确认

<a id="s3"></a>

#### 事实

- 从文档到实现执行`事实复核`：复核范围内每份当前事实文档、陈述和 `evidence`。
- 范围内未复核的文档逐份记录未触及理由，供步骤 7 报告。
- 同时按加载质量清单审阅范围内文档结构（`full` 覆盖 `docs/**` 与根文档）。
  结构与契约问题记语义 finding；`agents.project_content` 记 warning。

加载质量清单：

- 入口不过载：
  - `README.md`、`PROJECT.md`、`AGENTS.md` 不复述事实页已记载的可观察契约。
  - 仅维护者需要的内容不进 `README.md`，进 `PROJECT.md` 或 `docs/README.md`
    指向的 `docs/system/` 主题叶。
  - 根 `README.md` 不写最短可运行路径、不写维护者入口；
    `user_guide` 非 `not_applicable` 时链到 `docs/user-guide/README.md`。
  - `PROJECT.md` 入口指向由 CLI 报 `project.entry_links`。
  - `AGENTS.md` 托管块必须项目无关；托管块外写栈、配置或行为契约记 warning
    `agents.project_content`，不是语义 finding。
  - `docs/README.md` 是文档入口，当前事实排在决策与工作记录之前，不链接空目录。
    按要找的主题只打开一份页面，不当作 Proposal/Bug 工作清单。
- 路由页只路由：
  - `system/overview.md`、`user-guide/README.md`、切面 `index.md` 不复述叶子契约，
    不集中承担 evidence。
  - 核心模块表形状由 CLI 报 `overview.core_modules`；
    人工审「不适用」是否属实、链接是否指向五类专用叶。
- 唯一归属：同一可观察契约只在一页；其他页只链接。
  - 对外能力在 `user-guide`，内部结构与仍生效约束在 `system/architecture`，
    内部契约在 `system/interfaces`。
  - 运行时配置、可观测性、错误、鉴权、限制与恢复住五类专用叶。
  - 测试分类、失败语义与 skip 住 `system/testing/` 主题叶。
- 主题叶按主题拆：一页混多个主题、或该拆未拆（含 `size.hard`）记为结构 finding。
  - 修复方向是拆页或下沉，不是压缩措辞。
- 读者分离：`user-guide` 只写使用者可观察的行为；维护者材料不混入。
  - 根 `README.md` 不写入仅维护者需要的手册。
- ADR：`docs/context/adr/` 不复述当前结构。
  - 仍生效约束若只写在 ADR 而 `system/architecture` 缺失，记为 finding。
  - ADR 不按实现对齐。
- 工作对象与调研：Proposal、Bug、Jot、research 未冒充当前事实、
  未被 `docs/README.md` 当成通读清单即可。
  - 不做拆页 refine。`docs/repowiki/` 不审、不改。
- `docs/system/testing/<suite>.md` 的入口命令行：整段是命令，或以 `# ` 开头写文字；二者不得混排。
- 文档结构：按 `references/doc-structure.md`。
  - 硬限制由 CLI 报 `prose.*`；人工审软限制与内容形态，大段文字改为列表、表格或图。

可选加速（见 `common.md`「Jev 可选加速」）：

- 时机：人工语义复核争议陈述时；tool 可用时。
- 调用：`noul`（是否被 evidence 支持），或 `score`
  （0=无问题 / 1=warning 级 / 2=须记 finding）。
- state：陈述与 evidence 摘录。
- 采信后仍由主 Agent 写入 finding 文案；CLI 已报的 code ❌ 不改。
- 未采信走原复核。

验收：事实复核、加载质量发现、warning、未触及理由。

异常与交接：记录语义 finding 或 `agents.project_content` 后继续 4。

<a id="s4"></a>

#### 覆盖

从实现到文档复核对外可观察行为（`user-guide`）、系统边界、架构、接口、数据与运维实现。

验收：未记录实现、过时/错误陈述、不可验证 evidence 与计划混写 findings。

异常与交接：记录语义 finding 后继续 5。

<a id="s5"></a>

#### 警告

- 逐条审阅 CLI warning（`audit.uncovered`、`agents.size`）以及步骤 3 记下的
  `agents.project_content`。
- `.mdf/modules.yaml` 某 module 的 `ignore` 已覆盖 `AGENTS.md` 时，
  不再确认 `agents.size` 与 `agents.project_content`。

验收：

- 未被 evidence 引用且未被 ignorelist 覆盖的实现文件。
- 未忽略的 `agents.size` / `agents.project_content`。
- 逐条处置记录。

异常与交接：列入会话摘要后继续 6。

<a id="s6"></a>

#### 校验

- 运行 `validate --repo "$REPO_ROOT" --scope full`（即 full validation），不运行验证命令。
- migrate 只允许 `manifest.initializing` finding。

验收：validation findings。

通过条件：输出可解析且无 finding（migrate 仅余 `manifest.initializing`）；有 finding 时 CLI
退出码为 2，按未通过处理；无输出或不可解析同样未通过。

异常与交接：独立调用报告并停止；内部委托返回未通过，调用方走失败分支。

<a id="s7"></a>

#### 确认

返回审阅类型、两类范围、映射、warnings、复核文档、语义/validation findings 与未触及理由。

验收：会话摘要和用户当场确认。

- 确认单独提问，只问本次审阅结论是否确认，不与 Bug 分诊、收口、补验等其他决定放在同一问。
- 用户答复其他议题不视为确认。
- 本流程只向调用方返回确认原话与时间，不落盘。
  - 有材料目录的调用方写入并提交确认记录；主链（含经 fact update 委托）写
    `changes/unreleased/<slug>/fact-audit.md`（**report**，非 gate）。
  - 主链成功后将 `objectives.md` 的 fact audit 项改为 `[x]` 并提交。
  - 独立调用与独立 fact update 的委托无材料目录，不落盘，只在会话中确认。

通过条件：同时满足以下各项时通过；migrate 仅豁免 `manifest.initializing`。
validation 已由步骤 6 判定通过，本步不再复核。

- 无语义 finding（含结构 finding）。
- 无 `size.hard`、无 `prose.*`、无 `overview.core_modules`、无 `project.entry_links`。
- 无未确认 warning。
- 无其他 CLI finding（如 `modules.invalid`、`audit.scope`）。

该确认不跨调用复用。

异常与交接：存在其他 finding、未确认 warning 或未取得用户确认时：

- 报告审阅未通过、阻断原因与待确认项，不得称审阅通过。
- 独立调用报告后结束。
- 其他未通过时，内部委托返回未通过，调用方走失败分支。
  不得推进依赖审阅通过的步骤。
- 调用方是 fact-update，且未通过项只有结构 finding 时，返回「仅结构 finding」。
  fact-update 进入其步骤 4，不走失败停止。
  - 结构 finding 指加载质量清单、`size.hard`、`prose.*`、`overview.core_modules`、`project.entry_links`。
- 修复、补充确认或重审由调用方按其契约处理；fact audit 保持只读，不自行修复或自动重试。

Audit 不检查以下内容；这些属于 `$mdf close-out` 的交付前检查：

- Gitflow 分支、变更 diff。
- Proposal、Bug、Change、release 输入。
- closeout 或 merge 条件。

### 审阅类型

- `全量审阅`（`--scope full`）：从文档和实现两个方向覆盖全部当前事实文档与实现面。
  - 同时按加载质量清单覆盖 `docs/**` 与根文档。
- `范围审阅`（`--scope branch` 或 `paths`）：从文档和实现两个方向覆盖起点以来或
  调用方给定的实现与文档范围。
  - 结构检查只及范围内页面与改动到的入口页。
