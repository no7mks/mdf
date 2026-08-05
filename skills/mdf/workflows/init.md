# Init

它将仓库现有材料收敛到 MDF 的当前结构，并在`事实复核`后使 `manifest` 进入
`ready`。不要自动 commit。

完整读取 `workflows/common.md`、`workflows/grill.md`、
`references/repository-contract.md`。

## 1. 入口检查

1. 在外层工作流入口确认 worktree clean，解析 Git 根为 `REPO_ROOT`，运行：

   ```bash
   python3 "$MDF_ROOT/scripts/mdf.py" doctor --repo "$REPO_ROOT"
   ```

2. 若远端默认分支为 `main`，停止并要求用户先将其改为 `master`；不得自动改名。
3. 本次写入会使 worktree 变 dirty。用户对中间结果提出反馈时，继续当前流程，
   不得重复入口检查。

## 2. 盘点与归类

1. 盘点全部顶层项目项，区分 MDF 固定项、仓库治理文件、生态所需入口、业务实现、
   测试、生成物和文档；不得仅按现有目录名或 README 描述直接保留。
2. 对每个非生态必需且非 MDF 固定的顶层目录，通过内部 grill 工作流一次一题决定
   目录去处或顶层例外。仅含 `.gitkeep` 的占位目录按其未来职责迁移；业务实现目录
   建议迁入 `src/<目录>`，测试目录建议迁入 `tests/<目录>`。迁移目标已有实际内容时，
   在同一方案中移除 `.gitkeep`；目标仍为空时保留。不得在未经确认时迁移或删除。
3. 检查项目原有的全部文档，按仓库契约提出`当前事实文档`、已确认决策和其他材料的
   归类。此步骤只确定材料去处，不做`事实复核`或事实正确性判断。
4. 将非事实材料归入契约规定的位置。例如调研材料属于 `docs/research/`，已确认
   决策属于 `docs/adr/`。无法分类时一次只询问一个问题。
5. 通过内部 grill 工作流一次一题收敛需用户决定的事项，并从仓库证据收敛八项
   `基线`、最近稳定版本和非空 `verification.commands`。从未发布时最近稳定版本
   为 `none`。
6. 形成`初始化方案`：受影响路径、材料的去处、保留内容、顶层允许清单、业务实现与
   测试目录、拟补字段、`基线`、`验证命令`和预期 `validation`。只有用户明确确认
   后才可写入。

移动或删除既有内容时，方案必须列出源、目标和无信息损失的理由；不得覆盖既有
内容。任何配置调整均须重新显式调用 `$mdf init`，不得绕过本工作流直接改
`manifest`。

## 3. 落地初始化方案

1. 用户确认后执行 `init`，建立完整 scaffold。需要回退时使用 Git。
2. `manifest` 保持 `initializing`，`verification.commands` 初始为空。项目原有文档
   与经确认迁移的顶层项目项仅可按`初始化方案`归位、保留或排除；保留 `AGENTS.md`
   的非 MDF 托管块。
3. 按确认方案处理项目原有文档和顶层项目项，完成材料归位、`当前事实文档`、ADR、
   `README.md`、`PROJECT.md` 和`验证命令`。在 `PROJECT.md` 记录仅含例外的顶层
   允许清单及业务实现、测试和生成物目录。按`根文档职责`补齐或修订 `README.md`、
   `PROJECT.md`、`AGENTS.md` 与 `GLOSSARY.md`；若`初始化方案`调整仓库既有结构，
   审视 `README.md` 的用户和维护者入口、`PROJECT.md` 的维护手册与`当前事实文档`，
   消除重复或冗余内容。
4. 停止前逐项核对：每份既有文档和顶层项目项均已归位、保留或获用户明确排除；
   固定布局完整；`PROJECT.md` 已记录仅含例外的顶层允许清单及目录约定；`README.md`、
   `PROJECT.md`、`AGENTS.md` 与 `GLOSSARY.md` 各自符合`根文档职责`；文档入口可达；
   没有未说明的遗留文件。

## 4. 审计当前事实

比较本次调用前后的 `GLOSSARY.md`、`docs/product/**` 与 `docs/system/**`。内部委托
`audit` 执行`全量审阅`；它执行双向`事实复核`和 `full validation`。此时允许唯一的
`manifest.initializing` finding。

若任一`当前事实文档`新增或修改，`manifest` 必须保持 `initializing`；展示 audit
结果与 diff 并停止，要求用户复核、commit 后再次显式调用 `$mdf init`。

## 5. 续办

1. 续办时不得再改`当前事实文档`。运行 `full validation`，只接受
   `manifest.initializing` finding。
2. 没有其他 finding 时才改为 `ready`，并再次运行 `full validation`。
3. 若本次完全未改`当前事实文档`、八项`基线`和非空`验证命令`均可验证，可直接
   执行本节。
   任何失败均保留现场并报告 findings。
