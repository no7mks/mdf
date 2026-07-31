# Init Repo

只在用户显式调用 `$mdf init-repo` 时执行。将为当前 Git 仓库建立或更新 MDF
文档系统；我会先检查仓库证据，再一次确认一个必要事实。不要自动 commit。

完整读取 `workflows/common.md`、`workflows/grill.md`、
`references/repository-contract.md` 与 `references/workflows.md`。

1. 解析目标 Git 根为 `REPO_ROOT`，然后运行：

   ```bash
   python3 "$MDF_ROOT/scripts/mdf.py" doctor --repo "$REPO_ROOT"
   ```

   若远端默认分支为 `main`，停止并要求用户先将其改为 `master`；不得自动改名。

2. canonical 路径已有内容时，先展示完整写入方案：受影响路径、保留内容、
   拟补字段、八项基线、最近稳定版本、验证命令和预期 validation。只有用户
   明确确认后才可写入；不得自动覆盖、移动或删除既有内容。
3. 通过内部 grill 工作流一次一题收敛以下信息，并先从仓库证据确认事实：
   - 八项基线：glossary、product reference、system boundary、architecture、
     interfaces、data、operations、deviations；每项为已验证的
     `documented:<repo-relative-path>`，或有明确理由的
     `not_applicable:<reason>`；
   - 最近稳定版本：交叉核对既有材料、稳定版本根 CHANGE 与 CHANGELOG；
     从未发布则为 `none`；
   - `verification.commands`：在目标仓库运行的非空受信任命令列表；其产物必须
     自行清理或被 `.gitignore` 忽略。

不把未知或未来计划写成当前事实。任何配置调整均须重新显式调用
`$mdf init-repo`，不得绕过本工作流直接改 manifest。

## 初始化与续办

1. 用户要求预览时才运行 `init --dry-run`；预览不替代写入方案确认。CLI `init`
   不接收验证命令参数。
2. 用户确认后执行 `init`。它先写 scaffold，manifest 保持 `initializing` 且
   `verification.commands: []`；再按确认方案写验证命令，并保留 `AGENTS.md`
   的非 MDF 托管块。
3. 比较本次调用前后的 `CONTEXT.md`、`docs/product/**`、`docs/system/**`。
   任一事实页新增或修改时，manifest 必须保持 `initializing`；展示 diff 并停止，
   要求用户复核、commit 后再次显式调用 `$mdf init-repo`。
4. 续办时本次不得再改事实页。运行 full validation，只接受
   `manifest.initializing` finding；没有其他 finding 时才改为 `ready`，并再次
   运行 full validation。
5. 既有事实页本次完全未改、八项基线和非空验证命令都可验证时，可直接执行
   上一步。任何失败均保留现场并报告 findings。
