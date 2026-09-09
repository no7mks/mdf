# 初始化公共规则

由 init 与 bootstrap 按各自步骤读取；本文件不是用户 intent，不自行切换流程。
同时读取 `references/common.md` 与 `references/repository-contract.md`。

## 项目边界与分流

在任何写入前确定项目根 `REPO_ROOT`，读取起步材料并检查实际实现和运行证据。
不按仓库年龄、提交数量或文档数量判定。默认工程模板、README、需求草稿和选型材料
本身不代表已有业务；实际功能、接口、数据处理或已运行部署才构成既有项目事实。
部署配置可能只是模板，不能仅凭文件名判定；无法确定时先澄清。

先只读检查已有 `.mdf/manifest.yaml`：ready 表示已经接入 MDF，即使尚无业务也由
init 维护；initializing 不代表老仓库，应继续检查实际内容。不符合当前契约的既有
MDF 内容报告后停止，不推断历史语义。既有内容的校验在 Git 基础准备后执行。

| 调用 | 项目状态 | 行为 |
| --- | --- | --- |
| init | 未就绪且没有实际实现或运行事实 | 说明依据，内部转入 bootstrap，返回其结果 |
| init | 已有事实或已 ready | 继续 init |
| bootstrap | 已有实际实现或运行事实 | 写入前报错、列证据并提示 `$mdf init` |
| bootstrap | 已 ready | 停止，配置调整提示 `$mdf init` |
| bootstrap | 未初始化或 initializing，且符合新仓库条件 | 建立起点或核对已有产物续办 |

## Git 基础

入口允许普通目录和无提交的 Git 仓库。先用 `git rev-parse --show-toplevel` 检查边界；
位于其他仓库内部时先澄清，不直接嵌套 `git init`，不把父仓库默认为目标。
bootstrap 必须先通过新仓库判定，再执行本节，不能在拒绝老仓库前写入 `.git/`。

确认纳管范围、忽略规则和分支调整方案后，由 Agent 完成 Git 化：

- 非 Git 项目执行 `git init --initial-branch=master`。先提交应纳管的既有项目内容作为
  原始基线，再整理 MDF；空目录没有可提交内容时，不创建空提交，首个提交保存 MDF 起点。
- 已有 Git 历史保留。识别 staged、unstaged 和 untracked 改动，按公共规则确定归属，
  不通过提交全部改动换取 clean。没有提交身份时询问用户，不编造身份或修改全局配置。
- 新仓库在 master 上落地。既有 main、缺少 master、当前工作分支或远端默认分支
  不符合约定时，展示具体本地调整方案；不得重置已有分支、改写历史或强制对齐。
  涉及已有 master 冲突、远端默认分支或保护规则时确认方案后处理，不只提示用户自行改名。
- 不要求远端；保留已有远端，不自动创建托管仓库或推送。远端设置变更按已确认方案授权，
  无法完成时明确交接。开分支、切换和合并前按操作要求检查工作区。

Git 基础准备后运行 `doctor`。未初始化允许继续；已有有效 manifest 允许 ready，或仅
`manifest.initializing` finding；其他 finding 报告后停止。CLI init 仍要求 Git 根目录，
不负责语义判定、Git 化、提交或启用；两个 intent 共用该 CLI，不新增 bootstrap CLI。

## 配置、提交与完成

从确认方案提供八项基线、最近稳定版本、非空 `verification.commands` 和
`implementation_roots`。从未发布时版本为 `none`；没有业务检查时可用 `git diff --check`。
不适用基线逐项给出真实理由，不用计划或占位事实页满足 documented。实现根可以为空目录；
默认使用 `src`，已有模板使用实际目录并在 PROJECT 说明，不为 bootstrap 重排模板。

调用 `init` CLI 时传入完整配置：重复 `--baseline`、`--implementation-root` 与
`--verification-item '{"id":"check","kind":"custom","command":"git diff --check"}'`。
更新时核对并保留未要求改变的配置，不依赖 CLI 默认值覆盖现有设置。已有根文档和
AGENTS 非 MDF 托管块必须保留；续办先检查 diff，只更新确认范围，不覆盖重建。

1. 完成材料与配置，保持 initializing；清除本次模板占位说明，提交可验证的阶段成果。
2. 按调用方验收：init 完成事实审阅，bootstrap 核对起步材料；均执行 full validation。
   bootstrap 不调用 fact audit，full validation 是确定性契约校验，不是事实审阅。
   initializing 阶段仅允许 `manifest.initializing` finding；其他 finding 修正、提交后重验。
3. 展示结果、八项基线、验证命令和分支方案，取得用户明确“结束初始化并启用正常工作流”确认。
4. 将 manifest 改为 ready，执行 full validation，零 finding 后提交就绪结果；提交后再次核验。
5. 确保本地 master、develop 可用。新仓库从包含已提交就绪结果的 master 创建 develop；
   已有分支保留，缺少 develop 时按确认方案从 master 创建，不重置、不强制对齐。
   既有分支关系影响使用时报告具体问题并按确认方案处理，通过后才宣布完成。

语义确认不因提交而省略。失败保留现场和阶段提交，不宣称已完成；同次可修复继续。
暂停后的调用重新检查入口与已有成果，不因需要手动 commit 而要求重调。
