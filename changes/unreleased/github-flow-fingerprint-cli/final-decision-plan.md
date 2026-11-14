# 最终决策版计划：github-flow-fingerprint-cli 后续工作

## 定位

- 基底：本 worktree 分支 `github-flow-fingerprint-cli`（实现提交止于 `b336e40`，其上仅有建议文档提交）。
- 需求真源：`~/Downloads/implementation_plan.md`（下称“原计划”）。
- 输入：三份建议 `next-step-suggestion-from-{agy,astra,opus}.md`（下称 agy / astra / opus）。
- 本文只做裁定，不声明任何修复已完成。
- 核实方式：逐条阅读当前源码；纯函数 probe 日志见 `.test-reports/20261114-115607-plan-probe.log`。

### 优先级定义

| 级别 | 含义 |
| --- | --- |
| P0 | 先做；代码正确性缺陷，会错误放行、错误阻断或污染缓存 |
| P1 | 合入前完成；功能闭环、门禁与 Skill 指令一致性 |
| P2 | 推迟；超出原计划或收益低，另立 Proposal |

### 核实结论图例

- 属实：源码或 probe 直接证明。
- 部分属实：现象存在，但建议的原因、范围或做法有偏差。
- 不属实：与当前源码不符。
- 无法验证：依赖本次不读的分支（AGY/CODEX）或须 E2E 复现。

## 来源映射表

| 编号 | 事项 | 级别 | agy | astra | opus |
| --- | --- | --- | --- | --- | --- |
| F01 | workflow switch 空闲态判定 | P0 | P0-2 | 1 | 1 |
| F02 | delivery route 的 PR mode 收尾 | P0 | P0-1 | 2 | 3 |
| F03 | 自定义 trunk 去 `master` 硬编码 | P0 | P0-3.3 | — | 2 |
| F04 | audit-push 与 sync 适配 trunk/support | P0 | P0-3.1/3.2 | 5 | 2 |
| F05 | release_head 固定与持久化 | P0 | P0-5.1 | 6 | 5 |
| F06 | catch-up-plan 漏判 | P0 | P0-6 | 8 | 6 |
| F07 | verify 凭证证据链 | P0 | P0-7 | 3 | 7 |
| F08 | github-flow hotfix 基线 | P0 | P0-4、§5.2 | 9 | 4 |
| F09 | verify 显式输入覆盖面 | P1 | P1-2 | 4 | 8 |
| F10 | review/fact 凭证加固 | P1 | P1-1 | 7 | 9 |
| F11 | complete-stage 加固 | P1 | P1-4 | 8 | 11 |
| F12 | support 线 Trunk-First 与 Bug 真源 | P1 | P1-3 | 9 | 10 |
| F13 | local 模式 release 冲突恢复 | P1 | P0-5.2 | 6 | P1 首项 |
| F14 | Skill references 与 README 对齐 | P1 | P1-5 | 10 | 12 |
| D1–D7 | 推迟项（见“推迟事项”） | P2 | 部分 | 部分 | P1 列表 |

## 依赖顺序

1. 先冻结两项开放问题（见末节 Q1、Q2）；Q2 只阻塞 F08 与 F12。
2. F03（trunk 感知的分支分类与 `trunk_branch` 替换）→ F01、F04。
3. F02、F06 相互独立，可与 2 并行。
4. F05 → F13。
5. F07 → F09 → F10（共用凭证存储与校验方式）。
6. F08 → F12。
7. F11 在 F02、F06 之后。
8. F14 最后，代码契约稳定后一次改写。

## P0 事项

### F01 workflow switch 空闲态判定

- 问题：未完成收口记录漏检；合法的自定义 trunk 与 `support/*` 被当成在途交付。
- 核实：属实，且比三份建议描述的更严重。
  - `workflow_switch.py:46` 只用 `folder.glob("*.json")`。
    `publish.py:9-29` 把 feature/bugfix/release 记录写到 `finish/<kind>/<x>.json`，hotfix slug 写到更深一层。
  - `tests/e2e/github_flow/test_workflow_config.py:112` 用扁平名 `feature-x.json`，掩盖了漏检。
  - probe：`occupies_delivery` 对 `support/1.2`、`trunk`、`production` 均返回 True；
    只有 `main` 被 `gitutil.py:165` 写死排除。
  - 新发现：`sync/<branch>`、`sync/history/...`、`integrate/<version>` 经 `state_path` 被当作 adhoc，
    落成扁平 `adhoc-<hash>.json`（probe 已证）。
    integration 记录永无 `completed` 字段，因此一次 release-integrate 后 switch 被永久阻断。
  - agy 所说“排除 `sync/history/` 子目录”前提不属实（该记录是扁平文件），但“历史记录不应阻断”的诉求成立。
- 决策：做。
- 改动范围：
  - `workspace/workflow_switch.py`：`_pending_finish_records` 改为递归扫描，并按记录类型判定是否完成。
  - `lifecycle/release_integration.py`（`record_path`）与 `workspace/sync_pull.py`：
    为 integration 与 sync 记录提供专用路径（`finish/integrate/`、`finish/sync/`），不再借用伪分支名。
    不识别旧扁平记录（遵守“不引入旧版兼容”）。
  - `workspace/gitutil.py`（`occupies_delivery`、`branch_details`）：接收 trunk，排除当前/目标 trunk 与 `support/*`。
  - `require_idle` 增加检查：所有关联 worktree clean 且无进行中的 merge/cherry-pick；不代为清理。
- 完成标准：
  - 嵌套的未完成 feature/release/hotfix 记录阻断；已完成记录不阻断。
  - integration 记录在对应 release 完成后不阻断；sync 历史记录不阻断。
  - `trunk: main`、`trunk: production`、存在 `support/1.2` 时可切换。
  - 真正在途的 feature、`qa/*`、`dev/*`、integration 分支仍阻断；失败时 manifest 未被修改。

### F02 delivery route 的 PR mode 收尾

- 问题：PR mode 的 checklist 止于 catch-up；全勾后 route 直接返回 `complete`，漏掉 pr 与 close-out。
- 核实：属实。`stage_route.py:62-63` 无条件返回 `complete`；`gitflow.py:262-263` 规定 PR mode 止于 catch-up。
- 决策：做。
- 改动范围：`lifecycle/stage_route.py`（`route`），读取 `publish.state_path` 的收口记录与 `configured(repo)["mode"]`。
  - 只有收口记录 `completed is True` 才返回 `complete`。
  - PR mode 无 `merge_commit` 时 `next = pr`；已有 `merge_commit` 时 `next = close-out`。
  - 等待态沿用现有规则：非 yolo 为 `awaiting_decision_confirmation`，yolo 为 `ready`。
- 完成标准：E2E 覆盖五态：无 PR、PR 等待合并、已合并未收尾、收尾完成、收尾失败后重试。
  只有收尾完成返回 `complete`。

### F03 自定义 trunk 去 `master` 硬编码

- 问题：原计划允许任意合法 trunk（含 gitflow + `main`），多条路径仍写死 `master`。
- 核实：属实。
  - `workspace/planning.py:170,191,196,230,249-254`（gitflow ensure/land）。
  - `lifecycle/late_decision.py:47-52,71,104,184`；`lifecycle/pull_finish.py:364-365,388`。
  - `lifecycle/odr_scope.py:51,135`、`odr_acceptance.py:18`；`cli.py:57-59` 的 `prepare-git` 没有 `--trunk`。
- 决策：做。CLI flag 名（如 `--from-master`）保持不变，内部基线取 `trunk_branch(repo)`。
- 改动范围：上述文件中的 `"master"` 字面量统一改为 `trunk_branch(repo)`；
  `workspace/git_ops.py`（`command_prepare_git`）与 `cli.py` 增加 `--trunk`。
- 完成标准：
  - `workflow: {model: gitflow, trunk: main}` 下 planning ensure/land、ODR 起点、PR close-out 各有 E2E。
  - 原有 `master` 默认配置的 gitflow suite 断言不改且全绿。
  - `rg '"master"' skills/mdf/scripts` 只剩 `DEFAULT_TRUNK` 与 CI 模板替换锚点。

### F04 audit-push 与 sync 适配 trunk 与 support

- 问题：CI 审计与 sync 只认 `master/develop`；github-flow 的 trunk 被当成 develop 处理。
- 核实：属实。
  - `inspection/push_audit.py:54-55` 对非 `master/develop` 报 `invalid_audit_target`；
    `:102` 只采集 `master`、`planning` 的来源证据。
  - `workspace/sync_pull.py:51-53`：trunk 等于 `integration_branch` 时 trivial 提交免 PR。
    同一提交在 CI 上按 `master` 规则会判为 `direct_trunk_commit` violation，两处不一致。
  - `sync_pull.py:57`：自定义 trunk 领先时调用 `audit` 会抛错，sync 预览中断。
  - `sync_pull.py:38,62` 对 trunk 返回 `dev_pr`，而 github-flow 的入口名是 `trunk-pr`。
- 决策：做。
  - audit 从 `before` 提交读取 workflow；允许审计 trunk 与 `support/*`；平台 merge `support/* → trunk` 判为 violation。
  - github-flow 下关闭 planning 与 maintenance 直推豁免；trivial 豁免只保留给 gitflow 的 develop。
  - 动作名区分 `trunk_pr` 与 `dev_pr`。
  - sync 对齐 `support/*` 不在原计划内，推迟（D4）。
- 改动范围：`inspection/push_audit.py`（`classify`、`audit`、`collect`）、`workspace/sync_pull.py`（`plans`）、
  `workspace/sync.py`（状态名）。
- 完成标准：`trunk: main` 与 `support/1.2` 上的 audit-push 与 sync 各有 E2E；
  覆盖平台 merge、直接 push、缺失证据、`support → trunk`；原 gitflow 的允许/拒绝断言不变。

### F05 release_head 固定与持久化

- 问题：integration 建立后 release 源分支继续前进，tag 仍打在旧 `release_head` 上。
- 核实：属实。
  - `release_integration.py:77` 只要求旧 `release_head` 是源分支的 ancestor，不要求相等。
  - 原计划要求 `release_head` 写入 `delivery.json` 与 finish 记录。
    当前只写 finish 与 integration 记录（`release_head` 仅出现在 publish、pull_publish、pull_finish、release_integration）。
  - `pull_publish.py:31` 的 `state.get("release_head") or state["head"]` 是当前直接 PR 路径的取值，
    不是旧版兼容；但存在两种取值形式，应收敛为一种。
- 决策：做。
  - release-closeout 定版后把 40 位 `release_head` 写入 `delivery.json` 并提交。
  - 直接 PR 路径在创建收口记录时显式写入 `release_head`，删除 `or state["head"]`。
  - `release-integrate` 遇到源分支 HEAD 不等于记录值时：
    尚未创建 PR 则更新记录并把新 HEAD 合入 integration 分支；PR 已存在或已合并则报 `release_head_changed`。
- 改动范围：`lifecycle/release_integration.py`（`command_release_integrate`）与 `lifecycle/pull_finish.py`。
  另含 `lifecycle/pull_publish.py`（`_publish_github_flow`）与 release-closeout 写 `delivery.json` 的位置。
- 完成标准：冻结后追加提交、PR 已存在时追加提交、trunk 再前进、重试，各有明确结果。
  GitHub Flow 断言 tag 精确等于 `release_head`；Gitflow 断言 tag 仍指向原 merge commit。

### F06 catch-up-plan 漏判

- 问题：两处漏判使 `review = skip` 假阳性。
- 核实：属实。
  - `catchup_plan.py:121-122` 的 `owned_code` 要求路径属于某个 module；根目录脚本、CI、lockfile 被忽略。
  - `catchup_plan.py:134` 的 `contract` 只取 `up_paths`；本分支自己改 `AGENTS.md` 或 manifest 不触发。
- 决策：做。不纳入 dirty 路径（见否决项 R3）。
- 改动范围：`lifecycle/catchup_plan.py`（`build_plan`）。
  - 无 module 归属但 `classify == "code"` 的路径计入 review 代码面。
  - `contract = (own_paths | up_paths | set(resolution)) & rule_paths(repo)`。
- 完成标准：两条新 E2E：“基线后只改无 module 的代码”与“本分支改 `AGENTS.md`”，均不输出 skip。
  现有 unknown merge 阻止 skip 的用例保持通过。

### F07 verify 凭证证据链

- 问题：证据缺失或被改仍命中；跨 worktree 引用会悬空；并发写与运行中改文件会污染缓存。
- 核实：属实。
  - probe：证据目录为空时 `reusable` 仍命中（`attestations.py:219` 只检查 `is_dir()`）。
  - `attestations.py:244` 记录源 worktree 的绝对路径；`_write`（`:191-196`）没有锁。
  - `record_result` 不在运行后重算输入 key；环境指纹不含 MDF 脚本摘要。
- 决策：做。保留 `git ls-files -s` 快照内核。
  - 写凭证时记录证据目录内每个文件的 SHA-256；命中时全部核验，再复制到当前 worktree 新报告目录。
  - 按 key 加 `fcntl.flock`，串行化同指纹的执行与写入。
  - 运行结束后重算 key；与运行前不一致时不写通过凭证。
  - 环境指纹加入 MDF scripts 摘要，复用 `fact_identity.tool_manifest`。
  - 读取时做结构校验，并拒绝越界路径与 symlink；凭证 JSON 自身 checksum 不做（见 R7）。
- 改动范围：`execution/attestations.py`（`reusable`、`record_result`、`reuse_detail`、`environment`）、
  `execution/project_verify.py`、`execution/module_verify.py` 的调用点。
- 完成标准：
  - 证据删除、清空、改写均 miss；删除源 worktree 后复制件仍可用。
  - 两个进程并发跑同指纹只有一次实跑；运行中改输入不写凭证。
  - 命中时不启动子进程；报告保留 `original_duration_s`、`check_duration_s`、`reused_from`。

### F08 github-flow hotfix 基线

- 问题：只有一条已发布线且未传 `--support` 时，hotfix 从 trunk 切出，可能把未发布提交发进补丁。
- 核实：属实（行为）；是否违约为契约问题。
  - `support_line.py:49-54` 单线直接返回 `(trunk, None)`。
  - 原计划只写“多线时须 `--support`”；README `:124` 也暗含单线可从 trunk 出发。
- 决策：按 Q2 推荐方案做；用户否决则不做，仅在 F14 写清风险。
  - 推荐：存在已发布 tag 时 hotfix 一律走 `support/<major.minor>`；单线时自动解析，可省略 `--support`。
  - 无任何发布 tag 时报错，提示走 bugfix 合入 trunk。
- 改动范围：`lifecycle/support_line.py`（`hotfix_base`、`release_lines` 合并已有 `support/*` 分支计数）、
  `lifecycle/hotfix_version.py`。
- 完成标准：单线场景从 support 切出，补丁精确不含 trunk 未发布提交；无 tag 时报错；多线规则不变。

## P1 事项

### F09 verify 显式输入覆盖面

- 问题：lint/build 无法声明 module 外输入；被 gitignore 的显式输入不进指纹。
- 核实：
  - 属实：`modules.py:23-24,433` 只在 `SuiteEntry` 上支持 `extra_inputs`、`external_state`。
  - 属实：`attestations.py:55-60` 的快照用 `--exclude-standard`，ignored 文件取不到。
  - 部分属实：原计划的 E 包含“manifest 的 rules”；当前只有 manifest 本身，被引用的规则文件按纯文档排除。
  - 无法验证：AGY `lstrip("./")` 缺陷；本分支未使用该写法，只作为禁止事项。
- 决策：做 module 级字段、ignored 显式 glob 展开、rules 引用文件纳入 E。
  CLI 临时参数与 `<MISSING>` 哨兵不做（R1、R2）。
- 改动范围：`execution/modules.py`（`Module` 解析）、`execution/attestations.py`（`explicit_inputs`、`snapshot`）。
  路径归一化只用 `removeprefix("./")`。
- 完成标准：`.github/**`、被 ignore 的显式输入、rules 文件的变化各自 miss；
  只改交付进度文件（objectives、delivery.json）仍命中；`external_state` 的 module 不复用。

### F10 review/fact 凭证加固

- 问题：失败不吊销旧 pass；记录凭证时信任 context 文件；fact 复用未绑定 warnings。
- 核实：
  - 属实：`reviewing/report.py:132-133` 与 `fact_report.py:73-74` 只在 pass 时写，失败不写 tombstone。
  - 属实：`credentials.py:103-109` 直接取 `context["credential"]`，不从仓库现场重算。
  - 部分属实：fact identity 已含 manifest、modules、`AGENTS.md`（`fact_identity.py:27`），
    但不含被引用的规则文件；凭证不含 warnings 与 against。
  - 属实：`cli.py:87-97` 的 `fact-audit` 无 `--force`，原计划流程图要求三类都有。
- 决策：做。
  - code-review 与 fact 的非 pass 结论写 `failed` tombstone，阻断同 key 复用。
  - 记录前从仓库现场重算 identity 与 `rules_sha256`，不一致则拒写。
  - fact 凭证记录归一化 warning 键；只有当前 warning 是已审集合的子集才复用。
  - `fact-audit` 增加 `--force`。
- 改动范围：`reviewing/credentials.py`、`reviewing/report.py`、`reviewing/fact_report.py`、
  `reviewing/fact_identity.py`、`inspection/audit.py`（`_reuse`）、`cli.py`。
- 完成标准：先 pass 后 changes_requested 不再命中；新 warning 使复用 miss；篡改后的 context 拒写；
  `--force` 时不返回 reuse。

### F11 complete-stage 加固

- 问题：verify 证据校验比 `valid_branch` 松；Git 进行中操作与提交失败后的残留无保护。
- 核实：
  - 属实：`stage_route.py:27-43` 只看 `all_passed`、scope、branch；`module_verify.py:161-175` 已有 suites 核对。
  - 属实：写 objectives 前不检查 `MERGE_HEAD`；提交失败后残留的勾选会触发 `dirty_stage_files`（`:130-131`）。
  - 不属实：建议的 `commit --only`。`:139` 的 `git commit -- <paths>` 默认就是 only 语义。
- 决策：做。
  - branch scope 复用 `valid_branch`；smart scope 要求 `results` 非空且逐项 passed。
  - 写入前拒绝进行中的 Git 操作；确认当前位于交付 owner worktree。
  - 残留内容恰为本阶段勾选（及基线行）时允许续提交。
  - catch-up 阶段拒绝存在非材料路径未提交改动的工作区（替代 R3）。
- 改动范围：`lifecycle/stage_route.py`（`_verify_evidence`、`complete_stage`、`_already_done`）。
- 完成标准：缺 suite、空 results、进行中 merge、提交失败后重试、dirty 代码路径五个用例；
  无关 staged 文件仍不被提交。

### F12 support 线 Trunk-First 与 Bug 真源

- 问题：`urgent_support_first` 只校验 reason；维护线可以改 `docs/bugs/*`。
- 核实：
  - 属实：`support_line.py:131-133` 不核对 trunk 上的 Bug 是否存在且 open。
  - 属实：`commands_release.py:79-93` 无 `docs/bugs/*` 改动拦截。
  - 待复现：维护线首次切出时继承的 Bug 文档如何影响 `fixed` 校验，须先写 failing test。
- 决策：做门禁，不做删除（R5）。
  - `urgent_support_first` 核验 trunk 上 Bug 存在且 open。
  - support 及其 hotfix 分支禁止增删改 `docs/bugs/bug-*.md`；发布前再次核验 Trunk-First。
  - 远端已有 `origin/support/<line>` 时优先追踪远端。
- 改动范围：`lifecycle/support_line.py`（`verify_trunk_first`、`ensure_support_branch`）、
  `lifecycle/commands_release.py`（`_apply_trunk_first`）、发布前核验入口。
- 完成标准：trunk Bug 不存在或已 closed 时 urgent 被拒；support 上改 Bug 文档被拒；伪造 source_commit 被拒。

### F13 local 模式 release 冲突恢复

- 问题：local 模式下冻结切点 release 与前进后的 trunk 冲突时，没有引导的恢复路径。
- 核实：部分属实。
  - `gitflow.py:410-414` 冲突时 abort；`release-integrate` 只支持 github-flow + pr（`release_integration.py:66-67`）。
  - 但 `publish.py:108-112` 已接受“包含 before 与 release_head 的冲突解决提交”。
    这与原计划“local 在 trunk 上合入 release_head 或其冲突解决提交”一致，只是没有文档与测试。
- 决策：做文档与测试，不新建 local integration worktree（R10）。
  - 冲突错误的 details 给出恢复步骤：在 trunk worktree 手工 `merge --no-ff <release_head>`，解决冲突并提交后重跑。
- 改动范围：`workspace/gitflow.py`（`_merge` 的错误 details）、`lifecycle/publish.py`、`close-out.md` 对应段。
- 完成标准：E2E：冲突 → 按提示手工解决 → 重跑 close-out → tag 精确等于 `release_head` 且可达。

### F14 Skill references 与 README 对齐

- 问题：Skill 文档是 Agent 的执行指令；github-flow 仓库会读到只适用于 gitflow 的指令。
- 核实：属实。
  - 只有 `help.md`、`repository-contract.md`、`trunk-pr.md` 提到 github-flow。
  - `start.md`、`initialization.md`、`close-out.md`、`to.md`、`hotfix-version.md`、`late-decision.md`、
    `pr-close-out.md` 均写死 master/develop 且无 trunk 表述。
  - 新发现：`deliver.md` 未引用 `delivery route` 与 `complete-stage`，原计划 C1 的 CLI 未接入主循环。
  - 部分属实：`fact-audit.md:118-125` 仍要求 Agent 自行维护三组计数；`common.md` 已按 C2 精简。
- 决策：做定向修订，不以 AGY 的整批改写为底稿（R6）。
- 改动范围：上列 references、`deliver.md`、`close-out.md`、`code-review.md`、`fact-audit.md`、
  `README.md`、`GLOSSARY.md`、`SKILL.md`、`modules.md`、`docs/system/interfaces/mdf-cli*.md`。
  按 `doc-structure.md` 写，单文件 ≤500 行；超限按主题拆分。
- 完成标准：
  - `python -m pytest tests/lint` 通过（含 prose、行宽、行数；`prose_baseline.txt` 只减不增）。
  - github-flow 相关入口不再出现指向 develop 的无条件指令。
  - `deliver.md` 以 route 的 state 驱动下一步。
  - 文档中的 CLI 参数与 `mdf.py <cmd> --help` 一致。

## 推迟事项（P2）

| 编号 | 事项 | 来源 | 推迟理由 |
| --- | --- | --- | --- |
| D1 | CI `assets/ci/review.py` 接入凭证与 `--force` | agy、astra、opus | CI 的 git common dir 多为一次性，命中率低；先稳定本地凭证格式 |
| D2 | review-prepare 用 `measure_code` 实测体积 | astra、opus | 当前已有 numstat 行数；结构限制由 lint 负责 |
| D3 | release `combination_impacts` 结构化扩展 | astra、opus | `credentials.py:79-100` 已覆盖净增量、多交付共改文件与 module 接口层 |
| D4 | sync 对齐 `support/*` | agy、opus | 原计划未要求；support 推送已由发布流程负责 |
| D5 | 缓存 `check-ref-format` 结果 | opus | 纯性能项，无正确性影响 |
| D6 | 契约 lint 测试 | agy、opus | 字符串存在不能证明行为；先用 F01–F14 的行为测试 |
| D7 | verify 环境变量白名单 | agy、opus | 原计划环境指纹未列环境变量；白名单取值需单独讨论 |

## 否决事项

| 编号 | 建议 | 来源 | 否决理由 |
| --- | --- | --- | --- |
| R1 | `verify --extra-inputs/--external-state` CLI 参数 | agy、opus | 原计划未要求；指纹会依赖调用参数，同一内容出现多个 key |
| R2 | 缺失显式输入的 `<MISSING>` 哨兵 | agy、opus | F09 展开 ignored glob 后，文件出现即改变输入集，哨兵冗余 |
| R3 | catch-up-plan 把 dirty 路径计入计划 | agy、opus | 原计划范围为 `base..HEAD`；改为在 F11 拒绝 dirty 代码路径 |
| R4 | review 覆盖只接受单条凭证的超集 | opus | 会破坏增量轮次的逐文件复用；交互面已由 interaction 集兜底 |
| R5 | support 首次切出时删除继承的 Bug 文档 | agy | 违反“不得删除 `docs/` 产出物”；改用 F12 的改动门禁 |
| R6 | 以 AGY 约 41 份 references 改写为底稿 | opus | 夹带错误语义与无关 diff；agy、astra 均反对整批引入 |
| R7 | 凭证 JSON 自身 checksum | agy、opus | 读写同一信任域；证据文件摘要与结构校验已覆盖篡改与损坏 |
| R8 | 以耗时对比作为取舍依据 | agy | astra 已指出运行条件不等价；opus 也不采用 |
| R9 | 为 local 模式新建 `codex/integrate` worktree | agy、opus | 现有路径已符合原计划，见 F13 |

三份建议共同列出的“不吸收”清单全部维持：

- CODEX 把 `delivery.json` 纳入 verify 指纹；CODEX 用 `split("/")[0]` 判断保留名。
- AGY 的 complete-stage 代勾 code-review/fact/lint；AGY 改变 gitflow tag 位置、gitflow 允许 `--from-commit`。
- AGY 的旧 finish 记录回退分支；AGY 的跨测试模块 import。
- 本分支均未出现上述写法；共享 fixture 继续放 `tests/support_*.py`。

## 验证与留痕要求

| 时机 | 命令 | 报告 |
| --- | --- | --- |
| 每项改动 | `python -m pytest tests/lint`、`python -m compileall -q skills/mdf/scripts` | lint 读 JUnit；compileall 无报告时 tee 到 `.test-reports/<ts>-build.log` |
| 每项改动 | `python -m pytest tests/unit` 加该项新增的 E2E 文件 | `.test-reports/` 下 JUnit |
| 全部完成 | smoke：`python -m pytest tests/unit tests/e2e -m 'not release_only'` | 核对 300s 预算 |
| 合入前 | release 冷跑：`python -m pytest tests/unit tests/e2e` | 从同一份 JUnit 提取 quick 与 named suite |

- 每项先写 failing test 证明缺陷，再修复；不得改旧断言来消除失败。
- 失败先读报告与日志，不为查看输出而重跑。
- 代码文件 ≤1000 行，手写文本 ≤500 行，单行显示宽度 ≤180；超限按职责拆分，结果不超过 70%。
- 每组完成即提交，Conventional Commit，中文描述；不 rebase。
- 只在本分支开发；合入 `master` 使用 no-ff merge（非同名分支禁止 ff-only）。

## 风险

- F01 改动 integration 与 sync 记录路径：进行中的旧扁平记录不再识别。
  按契约不做兼容，切换前须确保无在途 integration/sync。
- F03 涉及 gitflow 主路径：以原有 gitflow suite 全绿作为回归门槛。
- F07 增加加锁与证据复制：须测量命中核验开销，避免 smoke 超出预算。
- F14 改写量大：须在 F01–F13 稳定后一次完成，避免反复改写。

## 开放问题（须用户拍板）

### Q1 `--yolo` 是否跳过设计确认

- 现状：`42b3c0c` 让 route 在 yolo 下对 design 返回 `ready`。
- 支持保留：`deliver-policy.md:105` 规定 yolo 不设 confidence 限制，由主 Agent 自裁定。
  README 也写明 yolo 开始自动推进后不再询问流程决策。
- 支持回退：原计划 C1 写“对设计确认、人工编码勾选、非 yolo 的 pr/close-out 确认显式返回等待状态”。
  agy、opus 按字面理解为设计确认始终等待。
- 无法裁定的原因：两份契约文本冲突，且 `42b3c0c` 是专门提交的行为变更。
- 推荐：保留现状（与 deliver 契约一致），并在 F14 中写明。

### Q2 github-flow 单线 hotfix 是否一律走 support 线

- 选项 A（推荐）：有发布 tag 即走 `support/<major.minor>`，单线可省略 `--support`；无 tag 报错并改走 bugfix。
- 选项 B：保持现状（单线从 trunk 切出），只在文档中提示未发布提交的风险。
- 无法裁定的原因：原计划与 README 字面允许 B；A 改变用户可见入口行为。
- 影响：决定 F08 是否实施，以及 F12 的测试矩阵。
