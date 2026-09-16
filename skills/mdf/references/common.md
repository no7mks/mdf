# MDF 公共意图规则

由调用方读取；这些规则按事件持续适用，不是依次执行的阶段。
进入 intent、收到反馈、调用 CLI、写入失败或提交时应用对应规则；
返回调用方不解除其他适用约束，完成后继续调用方当前步骤。
upgrade 不读取本文件。

## 工具

需要确定性操作时使用 `python3 "$MDF_ROOT/scripts/mdf.py"`，语义判断留给 intent。

每次 CLI 调用记录实际命令、输入、退出状态与结构化结果，并按当前步骤检查预期产物。
除 intent 明确声明的例外外，非零退出或产物缺失均走该步骤的失败去向，不以摘要代替检查。

验收：CLI 调用、产物检查与 intent 判断各自可追溯。非零退出或产物缺失走该步失败去向。
「异常」仅指禁止用 CLI 模拟语义判断；此时停止，不另走失败去向。

## 目标根

<a id="s-root"></a>

next 先按其流程识别目标，允许续办尚未 Git 化的初始化与无需仓库的 clarify。
除 init/bootstrap/migrate/next 外，执行仓库操作的 intent 在本次调用中先将用户指定目标或当前目录
用 `git -C <目标目录> rev-parse --show-toplevel` 解析为绝对 `REPO_ROOT`，再读取并执行对应流程。
核对解析出的仓库确为用户目标；边界不明先澄清，澄清后重做本条；命令失败则报告并停止，
不使用空值或上次调用的变量。
clarify 与 help 不要求 Git 仓库；init/bootstrap/migrate 由 initialization 公共流程处理普通目录
与父仓库边界。upgrade 解析 Git 根且不要求 manifest ready，规则见 `references/upgrade.md`。

## 切换工作区

<a id="s-switch"></a>

切换到已有 worktree 时，目标为绝对路径与完整分支名。已在该路径且当前分支
正确即通过；不得再 `git worktree add`，不得只在原根 `cd` 冒充已切换。

判定当前 agent：先看本会话可用工具，再看 `$MDF_ROOT` 是否位于
`.cursor/skills`、`.codex/skills`、`.kiro/skills`、`.claude/skills` 或
`.openclaw/skills`。工具与路径冲突时以工具为准。

Cursor：立即对目标路径调用 `move_agent_to_root`（参数 `rootPath`）。
禁止 `move_agent_to_cloned_root`（会 fetch origin，本地未推送分支会失败）。
调用后必须新开 shell 再核对，不得沿用切换前的终端 cwd。无该工具时报告缺失
并留在当前步骤，要求用户把工作区根打开为该路径。

Codex：要求用户把当前对话接到已有目标 worktree，不要再创建：
1. 点右上角 Environment 当前项（一般显示 Local）
2. Continue in 选 New local worktree，不要选 Cloud
3. 在 Hand off chat to worktree 中打开 Worktree 下拉，选名称等于
   目标分支的已有项（如 `feature/<slug>`）
4. 不要选 Create a new worktree
对话框会保持该 worktree 的既有分支。给出应选项后等待用户完成，再核对。

Kiro IDE：没有会话内切根工具。要求用户用 File > Open Folder 或
`kiro <路径>` 打开目标绝对路径作为工作区根；禁止 Add Folder to Workspace。
打开后在该根继续并核对。
Kiro CLI：会话绑定启动目录。要求用户在目标路径下重新启动 `kiro-cli`；
禁止只在原会话 `cd`。

Claude Code：对目标路径调用 `EnterWorktree`。路径不在 `.claude/worktrees/`
时需用户批准。禁止 `claude --worktree` 或在 `.claude/worktrees/` 另建副本。

其他（含 OpenClaw）：把目标绝对路径交给用户，要求把工作区或进程 cwd
打开到该路径后继续；禁止再创建 worktree。OpenClaw 不得用 `worktree: true`
另建 checkout，可用 `--cwd` 指向已有路径后重启。

核对必须在切换后的环境、新 shell 执行：`git rev-parse --show-toplevel`
等于目标路径，`git branch --show-current` 等于目标分支。向用户展示这两项。
未满足则留在当前步骤，重复对应指引，不拆除已建 worktree 与分支。

## 入口

<a id="s2"></a>

入口识别已有 staged、unstaged、untracked 改动，不普遍要求 clean worktree。
无关且不冲突的改动保留并继续；与任务重叠、归属或处理方式不明时先澄清，澄清后重做本条；
无法判定归属则停止。
clean 以 `git status --porcelain` 输出为空为准；不为 Skill 写入的文件设置额外豁免。

写入或提交前读取当前分支，按本次工作与文档的归属确定落点，不按 intent 名称分配
交付分支：

- master 不直接修改或提交内容，包括文档；hotfix 的修改也在 hotfix 分支完成。
  init/bootstrap/migrate 的初始化落地及 finish 的 Gitflow 合并按各自专门契约执行。
  upgrade 替换已安装 Skill 并提交本次路径时，可在当前分支（含 master）提交这些路径，
  不改 `.mdf/` 与 `docs/`；该例外只约束 upgrade，见 `references/upgrade.md`。
- 与当前交付分支工作相关的文档在当前分支更新，随该分支交付；包括规划记录、事实文档
  和 CodeWiki。当前事实文档和 CodeWiki 必须反映该 checkout 的实际状态，不把未实现
  的计划写成事实。调研、已确认决策与当前事实文档分开，不把候选方案当作已实现行为，
  不替代任务管理。
- 规划写入使用唯一的 `planning` 分支与仓库同级 `<repo-name>-worktrees/planning`
  worktree：覆盖 `prp create`、`prp review`、`prp split`、intake 中的 Proposal、
  以及 `jot promote` 为 Proposal。不在当前目录开分支，不占用 develop checkout。
  调用 `planning ensure --repo "$REPO_ROOT"` 创建或复用；当前根不是该 worktree 时，
  按「切换工作区」规则切过去，重新解析目标根。提交后运行
  `planning land --repo "$REPO_ROOT"`，在占用 develop 的 worktree（须 clean）上
  no-ff 合入。新建 Proposal 的 ID 在该工作区按当前 checkout 的 `docs/proposals/`
  最大序号加一分配；合入 develop 后才对 `$mdf start` 可见。
- 与当前交付分支工作无关、且不属于规划工作区的文档在 develop 更新；独立记录和公共
  文档维护也按此规则处理。develop 不存在时先明确创建基线，不擅自从未交付分支创建。
- 已有 Proposal 的修改若属于当前交付分支工作，仍在该交付分支更新；否则在 planning
  工作区更新并合入 develop。
- 归属不明确时先询问。需改用 develop 或 planning 时，在写入前选择安全切换或独立
  worktree，重新解析目标根并复查前置条件；不得自动搬运、暂存或提交已有改动来切换
  分支。无法安全准备目标时保留现场并停止。detached HEAD 下不写入或提交。

只读查询、审计和预览不受上述写入分支限制，报告其实际 checkout；
各交付阶段的角色分支、身份与 gate 限制仍须满足，不因文档相关而绕过。

验收：已有改动、当前任务范围和写入分支归属明确。
开分支、合并、版本收口及 CLI 明确要求 clean 的具体操作，
在执行前检查；不通过自动提交全部改动清场。只读与预览不整理、暂存或提交已有改动。

## 反馈

<a id="s3"></a>

同次 intent 接受用户对中间产物的反馈；不得仅因本次产物尚未提交而拒绝修改。
具体操作的前置条件仍须满足。

验收：用户反馈已被本步吸收，或明确无反馈。
异常与交接：边界不明则报告并停止；澄清后重做调用方当前步骤。

## 失败

<a id="s4"></a>

写入失败时保留现场并报告 findings，等待用户处理。

验收：失败现场、findings 与等待状态已报告。
异常与交接：本条即失败汇；不自行回滚，除非当前 intent 另有恢复规则。

## 交接

<a id="s5"></a>

Agent 可以主动创建本地提交，并应在形成有意义、可解释的阶段成果时及时提交。
允许如实标注未完成状态的阶段提交；提交不代表验收通过，也不替代用户对方案、状态或启用的确认。
用户明确要求暂不提交时遵从；无改动不创建空提交。中文 Conventional Commit 应准确描述内容和必要的未完成状态。

只暂存当前任务的明确路径或改动块，不夹带无关用户改动；同一文件混有无关改动也不能整文件顺带提交。
提交前核对完整 staged diff，已有无关暂存项也必须隔离，不能直接 commit 一并带入。
内部委托由外层 intent 统筹提交；各阶段要求的已提交基线和必须同批提交的产物仍有效。
只读、预览不产生提交；失败保留现场，可保存有价值且状态明确的阶段成果，不以 commit 冒充完成。

push、merge、tag 和删分支仍按各自流程授权，不从 commit 权限推导。禁止 rebase，不擅自改写已有历史；
异名分支使用 no-ff。阶段基线和集成要求见 `references/delivery-contract.md`。

规划 intent 在本次规划提交后运行 `planning land --repo "$REPO_ROOT"`，把
`planning` no-ff 合入占用 develop 的 worktree；无新提交则该命令为 no-op。
develop 占用者 dirty 时停止并报告，不改 checkout。

阶段提交后返回调用方继续当前流程；当前 intent 全部完成后才结束，
不仅为手动 commit 要求重调，也不自动触发下一个用户入口。

验收：提交范围、staged diff 与 Conventional Commit 可追溯，或明确无改动。
异常与交接：提交失败保留现场；只读、预览不产生提交。
deliver 依据 `references/deliver.md` 内部串联从 start 起的剩余交付阶段，子 intent 完成后返回 deliver 继续。
init 依据 `references/initialization.md` 自动转入 bootstrap 或 migrate 是明确的内部委托，不自动串联交付主线。

## 语言

<a id="s6"></a>

核对简体中文、英文保留范围与完整前缀 ID。
生成的 Markdown 正文、标题与列表使用简体中文；
仅代码、路径、标识符、 命令、 标准名称及无法准确翻译的专有术语保留英文原文。
对用户沟通及产出中的 Proposal、Bug、Jot 须写完整前缀 ID，不得省略前缀或只写序号/短码。
不符合时改写后再继续。

## 按需读取

按操作需要读取：`references/repository-contract.md` 定义仓库目录、`manifest` 与 `基线`；
`references/object-contract.md` 定义 Proposal、Bug 与 Change 的 schema 和不变量。
intent 声明读取的契约或模板缺失时停止并报告，不猜测内容。

| 材料 | 位置 | 读取条件 |
| --- | --- | --- |
| 意图 | `references/` | 读取显式调用命中的流程及其声明委托的内部流程 |
| 公共契约 | `references/` | 按 intent 指定读取目录、对象或 CodeWiki 契约 |
| 模板 | `assets/` | intent 要求写入仓库产出物时读取对应模板 |
| 确定性 CLI | `scripts/` | intent 要求确定性操作时调用 |
