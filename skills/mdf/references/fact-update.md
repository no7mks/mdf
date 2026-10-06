# Fact Update

工作分支上由主链在 **verify branch 之后、close-out 之前** 于 fact audit 未通过时委托；
无 fact stage gate。独立调用仍可用。

evidence 仅为 path 列表；怎么验归 modules 套件与 `$mdf verify`。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check and scope                │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 仓库已 ready 且 scope 明确
┌──────────────────────────────────┐
│ 2 Align facts                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 事实与实现一致
┌──────────────────────────────────┐
│ 3 Audit                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 其他未通过 ────→ [停止并报告]
                 ├──── 验证失败 ──────→ [停止并报告]
                 │
                 ▼ 验证通过且审阅通过或仅结构 finding
┌──────────────────────────────────┐
│ 4 Refine structure               │
└────────────────┬─────────────────┘
                 │
                 ├──── 第三次仍有结构 finding ────→ [停止并报告]
                 ├──── 失败/缺失 ─────────────────→ [停止并报告]
                 ├──── 有改写 ────────────────────→ 3 Audit
                 │
                 ▼ 无结构 finding
                 [结束]
```

## 工作流（唯一执行契约）

人工 feature 在 verify smoke 完成后直接调用本 intent，沿用内部 Audit 步骤。
全部完成后自勾 objectives 的 fact update 并提交；不新增独立 fact audit 步骤。


读取 `references/common.md` 与 `references/repository-contract.md`；
步骤 3 读取并内部执行 `references/fact-audit.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check and scope | 脚本 | 运行 doctor，确定 scope 与范围 | doctor、调用方、scope、路径 | 2 | 写入前停止并报告 |
| 2 | Align facts | 约束 | 按实现同步范围内当前事实、五类专用叶及 evidence | 事实 diff | 3 | 停止并报告 |
| 3 | Audit | 约束 | 委托同 scope 的 fact audit；按变更验证 | 审阅、验证 | 通过或仅结构则 4 | 其他未通过或验证失败则停 |
| 4 | Refine structure | 约束 | 改结构并提交 | 结构 diff、提交 | 未超次改写回 3；无 finding 结束 | 超次或无法改写则停 |

## 术语与数据结构

### 范围与写入边界

<a id="s1"></a>

**入口**

任何写入或提交前运行 `doctor --repo "$REPO_ROOT"`；
核对命令成功且结果包含 `is_git_root: true`、`initialized: true`、`state: ready`。

- 独立调用与主链委托均须满足。
- 未初始化、initializing 或 manifest 无法读取时提示 `$mdf init`，不写入、不提交。
- `layout.migrate` 或 `manifest.schema` finding 提示 `$mdf migrate`，本 intent 不搬布局。
- 工具失败或目标边界不符时报告并停止。
- 本步骤检查初始化状态，不将 `normal_workflows_allowed: true` 作为前置条件。
- 写入分支按 `common.md` 的归属规则检查；`branch.invalid` 不作为分支归属判断的替代。
- 已有 findings 如实记录，事实及 evidence 问题由步骤 2–4 按范围处理。
  - 其他超出本次范围的问题报告后停止，不借同步入口修改无关对象或配置。

`--scope` 与 fact audit 同义，三选一：

- `branch`：独立调用默认。
  - 起点与 `fact-audit.md` 相同，三级回退：
    - `delivery.json` 的 `start_commit`。
    - 否则 git config `branch.<owner 分支>.mdf-start-commit`。
    - 否则 `git merge-base develop HEAD`。
  - 范围是该起点以来实现改动该碰的事实页与被改到的路由链接，不是「分支上改过的 Markdown」。
  - 未改实现只想整理文档时显式用 `full`。
  - 主链 release 的 `--base` 为上一正式发布的 master commit/tag（与 code-review 同一左端点）；
    首次发布无上一版本时停止确认初始基线。
- `full`：知识面全树——`docs/user-guide/**`、`docs/system/**`、入口根文档、
  `docs/context/adr/` 的复述检查与全部体积。结构 finding 可全改。
- `paths`：调用方给出精确实现/文档路径；独立调用列出 `<path>...` 即此形式。
  - 路径分派与缺路径、与 `--scope full|branch` 同用时的处理同 `fact-audit.md`。

主链只能委托 `branch` 或等价 `paths`，不得改用 `full`；全库整理走显式
`$mdf fact update --scope full`。

支持用户独立调用；也由主链在 fact audit 后委托。

- 独立调用不要求交付分支或阶段记录，不触发交付。
  - 可在当前工作相关的 feature、bugfix、release 或 hotfix 分支同步事实。
  - 在途 feature 时只在 owner 工作，cwd 为 qa/dev 则切回 owner。
  - 无关的独立维护在 develop 完成，不在 master 写入。
- 主链调用采用固定起点到 HEAD 的精确范围：feature/bugfix/hotfix 为
  start_commit，release 为上一正式发布。

验收：doctor 结果、调用方类型、scope、事实与实现范围。

异常与交接：未初始化或范围不明时写入前停止并报告。

<a id="s2"></a>

**对齐**

只更新范围内受影响的当前事实及 evidence：

- `verification` 整段是命令，或以 `# ` 开头写文字；二者不得混排。
- 不修改 PRP、Bug、Change、objectives 或 design 的意图，不改 `docs/context/`、`docs/repowiki/`。
- `user-guide` 只在对外可观察行为有变时改；
  `system/architecture` 只在内部结构或仍生效约束有变时改。
- 范围内实现已有配置、可观测、错误、鉴权或限制与恢复的可观察契约时，
  写入对应五类专用叶，并把核心模块表该行改为链接。
  - 叶不存在则用下表模板新建。
  - 无该契约则不建叶、不改「不适用」行。不为凑表造页。
- 不为满足形式制造无关文档，不把计划写为当前事实。
- 测试运行器、验证配置、skip 或失败语义有变时同步 `docs/system/testing/` 主题叶。
  - 主题混杂或超 450 再拆，不预建空拆页。
- 实现有问题时报告，不用文案掩盖。
- 本步不做加载质量改写（拆页、复述改链接、路由瘦身）。

五类专用叶（页面均在 `docs/system/`，模板均在 `assets/templates/`）：

| 模块 | 页面 | 模板 |
| --- | --- | --- |
| 配置 | `operations/configuration.md` | `system-configuration.md` |
| 可观测性 | `operations/observability.md` | `system-observability.md` |
| 错误 | `interfaces/errors.md` | `system-errors.md` |
| 鉴权 | `interfaces/auth.md` | `system-auth.md` |
| 限制与恢复 | `operations/limits-and-recovery.md` | `system-limits-and-recovery.md` |

验收：事实 diff。

异常与交接：写入失败保留现场，停止并报告。

### 审阅与结构

<a id="s3"></a>

**审阅**

内部委托 fact audit 之前，先提交本次事实页，含新建或拆出的专用叶。

- full validation 按已提交内容判 `fact.untracked` 与 `evidence.stale`。
- 未提交的同次写入会变成其他未通过，到不了步骤 4。
- 主链委托时，这次事实提交由本 intent 完成。
  调用方随后提交 Change 等其余材料。
- 委托使用同一 `--scope` 与 `--base`。
  - `paths` 要把本次新建或拆出的页写入 `--document-path`。
  - `branch` 依赖已提交的 diff，未提交的新文件不在范围内。

- 只改事实文档不重跑业务验证。
- 实现、测试或 verification 配置变了，才重跑当前交付所需 suite。

结果分四类：

- 通过。
- 仅剩结构 finding：加载质量清单、`size.hard`、`prose.*`、`overview.core_modules`、`project.entry_links`。
- 其他未通过：事实错误、覆盖遗漏、validation 阻断、未确认 warning、未取得用户确认。
- 验证失败：所需验证命令失败或缺少结果。

验收：fact audit 结论、验证结果。

异常与交接：其他未通过或验证失败时停止并报告，不声称事实同步完成；
验证通过且审阅仅结构 finding 时进入 4。

<a id="s4"></a>

**结构**

只对步骤 3 记录的、且位于范围内的结构 finding 做最小改写：

- 拆页或下沉到主题叶。
- 把复述改为链接。
- 把只在 ADR 里的仍生效约束写入 `system/architecture` 并在 ADR 留链接。
- 瘦身路由页。
- 补核心模块表缺行或缺理由。
- 按上表模板建缺的五类专用叶。
- 在 `PROJECT.md` 写入 `docs/system/overview.md`、`docs/README.md` 与
  `docs/system/testing/index.md`。
- `prose.*`：按 `references/doc-structure.md` 结构化改写，规则同 `references/prettify.md`「检查与改写」。

不改承诺的行为，不改范围外页面，不为「顺手」重排文档树。

- 有改写则回到 3 重审；`4→3` 最多两次。这次重审不重跑 suite。
  - 重审前再次提交结构改写。
  - 仅 `--scope paths` 把新建或拆出的页并入 `--document-path`。
  - `branch` 与 `full` 保持原 scope，不附加路径。
  - 只改本次 audit 范围内的页面。
- 第三次仍有结构 finding（表中的超次 finding）则停止并报告，即使本步已经改写也不回 3。
- 无结构 finding 时无改写结束，含第三次审阅已通过。
- 仍有结构 finding 却无法改写时停止并报告，不按无改写结束。
- 无改写或重审通过后，事实页应已在审阅前提交。
  - 主链委托时不把事实页留到调用方。
  - ❌ 不再记录 fact-update stage gate。
  - 本次事实审阅确认与验证证据按 fact audit 的返回规则交接。

验收：结构 diff、适用提交；无 fact-update stage gate。

异常与交接：写入失败保留现场并停止，不按无改写结束；提交失败时停止并报告，不声称事实同步完成。
