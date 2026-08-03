# Init

只在用户显式调用 `$mdf init` 时执行。它将仓库现有材料收敛到 MDF 的当前
结构，并在`事实复核`后使 `manifest` 进入 `ready`。不要自动 commit。

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

## 2. 盘点现状

1. 检查 README 与现有 Markdown，按仓库契约区分`当前事实文档`、已确认决策和
   其他材料。`当前事实文档`必须有仓库内 `evidence`；未知内容不写成事实。
2. 将非事实材料归入契约规定的位置。例如调研材料属于 `docs/research/`，已确认
   决策属于 `docs/adr/`。无法分类时一次只询问一个问题。
3. 通过内部 grill 工作流一次一题收敛需用户决定的事项，并从仓库证据收敛八项
   `基线`、最近稳定版本和非空 `verification.commands`。从未发布时最近稳定版本
   为 `none`。
4. 形成完整写入方案：受影响路径、材料的去处、保留内容、拟补字段、`基线`、
   `验证命令`和预期 `validation`。只有用户明确确认后才可写入。

移动或删除既有内容时，方案必须列出源、目标和无信息损失的理由；不得覆盖既有
内容。任何配置调整均须重新显式调用 `$mdf init`，不得绕过本工作流直接改
`manifest`。

## 3. 建立初始化态

1. 仅在用户要求预览时运行 `init --dry-run`；预览不替代方案确认。CLI `init`
   不接收`验证命令`参数。
2. 用户确认后执行 `init`，建立完整 scaffold。`manifest` 保持 `initializing`，
   `verification.commands` 初始为空，并保留 `AGENTS.md` 的非 MDF 托管块。
3. 按确认方案完成材料归位、`当前事实文档`、ADR、README 导航和`验证命令`。
   README 只作导航，链接 `CONTEXT.md`、`docs/index.md` 及仓库已有的相关文档类别。
4. 停止前逐项核对：每份既有材料均已归位、保留或获用户明确排除；固定布局完整；
   README 与文档入口可达；没有未说明的遗留文件。

## 4. 审计当前事实

比较本次调用前后的 `CONTEXT.md`、`docs/product/**` 与 `docs/system/**`。内部委托
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
