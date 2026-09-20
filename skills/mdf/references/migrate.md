# Migrate

它接入已有项目或调整现有 MDF 配置，将既有材料收敛到当前结构，
经`当前事实文档`的事实复核后使 `manifest` 进入 `ready`。
接受 `$mdf init migrate` 或 `$mdf migrate` 显式调用，或 init 依据公共分流规则的内部委托。
新项目停止并提示 `$mdf bootstrap`。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check entry                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 未就绪的新项目 ────→ [停止并提示 bootstrap]
                 ├──── 边界不明 ──────────→ [澄清后返回 1]
                 ├──── 其他异常 ──────────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Inventory                      │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并澄清]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Clarify layout                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 未解决 ────→ 3 Clarify layout
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 4 Confirm plan                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 分类变化 ────────→ 2 Inventory
                 ├──── 其他方案变化 ────→ 3 Clarify layout
                 ├──── 未确认 ──────────→ 4 Confirm plan
                 │
                 ▼ 用户确认
┌──────────────────────────────────┐
│ 5 Initialize                     │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留现场，停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 6 Audit facts                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 审阅或校验未通过且可修复 ────→ 6 Audit facts
                 ├──── 无法继续 ────────────────────→ [保留现场并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 7 Enable workflows               │
└────────────────┬─────────────────┘
                 │
                 ├──── 事实变化 ────→ 6 Audit facts
                 ├──── 未确认 ──────→ [保持 initializing，结束]
                 ├──── 其他失败 ────→ [保留现场，停止]
                 └──── 通过 ────────→ [结束]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/initialization.md`、`references/common.md`、`references/clarify.md`
与 `references/repository-contract.md`。
接受用户显式调用 `$mdf init migrate` 或 `$mdf migrate`，或 init 依据公共分流规则的
内部委托；复用已确认信息，不重复提问。
步骤 6 读取并内部委托 `references/fact-audit.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check entry | 约束 | 只读判定分流 | 边界、事实、MDF 状态 | 2 | 不明回 1；新项目提示 bootstrap；其他停止 |
| 2 | Inventory | 约束 | 盘点全部顶层项和文档，按职责分类 | 完整分类清单 | 3 | 停止并澄清 |
| 3 | Clarify layout | 约束 | 调用 initialization #3 确认配置 | 逐项决定、完整配置 | 4 | 留在 3 澄清 |
| 4 | Confirm plan | 约束 | 展示源、目标、保留内容与初始化方案并确认 | 用户明确确认 | 5 | 未确认留在 4；分类 2；其他 3 |
| 5 | Initialize | 脚本 | 调用 initialization #2+#4：init、归位并提交 | 归位表、根文档、提交 | 6 | 保留现场，停止 |
| 6 | Audit facts | 约束 | 比较事实；提交后委托全量审阅并校验 | 事实复核、仅允许项 | 7 | 可修复则重验；无法继续则停止 |
| 7 | Enable workflows | 脚本 | 按序 initialization #6-8 | 确认、校验、提交 | 结束 | 事实变化 6；未确认则结束；否则停 |

## 术语与数据结构

### 入口与盘点

<a id="s1"></a>

**入口**

先按 `initialization.md` 只读确认项目边界、新旧与 MDF 状态。未就绪且符合新仓库
条件时停止，列依据并提示 `$mdf bootstrap`（或 `$mdf init`），提示前不写入 `.git/`。
已 ready 的空仓库仍在 migrate 调整配置。已有 Git 的非新项目必须运行 doctor；
尚未 Git 化的目录等到方案确认后由 initialization 段 2 准备 Git。不因普通目录、
无提交或 dirty 一概拒绝。doctor 报 `manifest.schema` 或 `layout.migrate`（manifest
或 `docs/` 布局不符合当前契约）是本 intent 的合法入口态，不是损坏：进入盘点，
由步骤 3 决定 `docs/product/`、`docs/adr/` 等目录的去处并重写 manifest。

验收：明确项目根、判定依据；已初始化仅允许 initializing finding、
`manifest.schema` 与 `layout.migrate` finding，或 ready 无 finding。

异常与交接：边界或改动归属不明时澄清，其他 finding 报告后停止。中间反馈继续本次流程，不重查入口。

<a id="s2"></a>

**盘点**

盘点全部顶层项目项并检查项目原有的全部文档，区分 MDF 固定项、治理/生态入口、实现、测试、 生成物与文档。

验收：分类清单。

异常与交接：停止并澄清。不得仅凭目录名或 README 保留；符合 CodeWiki 契约的 `docs/repowiki/`
留在原处且不纳入当前事实、ADR 或调研分类； 此步骤不做`事实复核`。

### 配置与确认方案

<a id="s3"></a>

**布局**

使用内部 clarify intent，议题为材料去处、顶层例外、基线与验证。
确认非生态必需且非 MDF 固定顶层目录的去处或顶层例外；本地或外部调研材料归入
`docs/context/research/`，已确认决策归入 `docs/context/adr/`，并从仓库证据收敛八项 `基线`、最近稳定版本与非空
`verification.commands`。`docs/` 内材料按 `repository-contract.md`「文档分类与
按需加载」归位：面向使用者的页面进 `docs/user-guide/`（`README.md` 只路由，
主题各一页）；边界、架构、接口、数据、运维进 `docs/system/` 对应切面的主题叶；
测试约定进 `docs/system/testing/`（已有根 `docs/testing.md` 则迁入该切面）；
缺 `index.md` 或主题叶时按模板补齐并按仓库证据填写；
`overview.md` 核心模块表按已有材料填链接或「不适用」，不批量创建空主题叶；
仍生效的架构约束从 ADR 抽到 `docs/system/architecture/`，ADR 只留理由；
`docs/product/`、`docs/adr/` 等不属于当前布局的目录在方案中列出逐文件去处，落地后
不得残留。`baselines` 键与路径按当前契约重写（含 `user_guide`），`schema_version`
写为当前值。每项为 id、kind、command；初始化 CLI 用重复的
`--verification-item '{"id":"check","kind":"custom","command":"git diff --check"}'` 传入。
已有未分层 commands 保持原样即可，行为与今天一致；若要分层，手工在同级补
`suites` 映射（含 `quick`），本 intent 不生成。

验收：逐项决定与验证命令。

异常与交接：无法分类时留在 3。仅含 `.gitkeep` 的占位目录按其未来职责迁移； 迁移目标已有实际内容时，
在同一方案中移除 `.gitkeep`，否则保留。单 module 的业务实现与测试建议迁入 `src/` 与
`tests/`；多 module 建议迁入或保留 `<module>/src/` 与 `<module>/tests/`，
不得摊平为仓库根 `src/<module>/` 与 `tests/<module>/`。但不得在未经确认时迁移或删除。
已接入 MDF 但暂无业务检查时可用 `git diff --check`；从未发布时最近稳定版本为
`none`。

<a id="s4"></a>

**方案**

形成`初始化方案`：路径、材料去处、保留内容、顶层允许清单、实现/测试目录、 拟补字段、基线、验证命令与预期
`validation`。

验收：用户明确确认。

异常与交接：用户尚未确认且方案未改时留在 4。材料分类有误时回到 2；去处、基线或验证命令需调整时回到 3。
移动/删除必须列出源、 目标和无信息损失理由，且不得覆盖既有内容。 不处理待实现意图；完成后用户可按输入形态显式
`$mdf intake` 或 `$mdf bug create` 或 `$mdf prp create`。配置调整必须再次显式调用
`$mdf init migrate`、`$mdf migrate` 或 `$mdf init`。

### 落地与启用

<a id="s5"></a>

**落地**

执行 `init` 建立或更新完整 scaffold 前，按 `initialization.md` 段 2 依已确认方案准备 Git
基础并运行 doctor。保持 manifest `initializing`，传入核对后的完整配置与验证命令，
并只按方案归位/保留/排除原材料与顶层项。配置更新保留未要求修改的字段，续办核对已有产物，
不覆盖重建；完成材料后创建本地阶段提交，再审阅事实。

验收：固定布局、完整归位核对表、 `README.md`、`PROJECT.md`、`AGENTS.md` 与 `GLOSSARY.md` 各自符合`根文档职责`
且入口可达、没有未说明的遗留文件。

异常与交接：保留现场与 findings，不自动回退；停止并报告。
项目原有文档 与经确认迁移的顶层项目项只可按方案归位、保留或排除；保留 `AGENTS.md` 非 MDF 托管块；
完成当前事实文档、ADR、 `README.md`、`PROJECT.md` 与验证命令；在 `PROJECT.md`
记录仅含例外的顶层允许清单与目录约定。 方案调整仓库结构时，审视 `README.md` 的用户/维护入口、`PROJECT.md`
的维护手册与当前事实文档，消除重复；此后新增或更新文档时保持该分工，
根文档不复述当前事实页的契约。

<a id="s6"></a>

**审阅**

比较调用前后的 `GLOSSARY.md`、`docs/user-guide/**`、`docs/system/**` 与 `docs/context/adr/**`，
内部委托 `fact audit` 执行`全量审阅`（`--scope full`）。
先提交本次事实与证据作为可审阅基线；审阅发现问题时修正、提交并重验，不要求用户手动 commit 后重调。

验收：事实复核、diff 与 full validation；仅允许 `manifest.initializing` finding。

通过条件：审阅与校验通过后进入 7。异常与交接：未确认的语义问题继续澄清；其他
finding 修正后重验，同一项两轮后仍在则无法继续；无法继续时保留现场并报告。
提交不替代事实复核或用户确认。

<a id="s7"></a>

**就绪**

按 `initialization.md` 的公共完成规则展示当前事实复核、八项基线、验证命令和分支方案；
取得用户明确“结束初始化并启用正常工作流”确认后改 ready，校验、提交并核对本地 master/develop。

验收：事实审阅有效、full validation 零 finding、就绪结果已提交、本地分支可用。

异常与交接：事实发生变化则返回 6 补审，不复用过期结论；用户未确认启用则保持
initializing 并结束，不写 ready。其他失败保留现场并报告，未通过不得宣称完成。
