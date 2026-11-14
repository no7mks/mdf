# 落地方案：`github-flow-fingerprint-cli` 评审修订与分批实施

本方案基于独立源码审计对 `final-decision-plan.md` 作出修订，并拆分为可独立提交的 8 个批次。

## 1. 评审结论摘要（相对决策版的修订清单）

本节列出独立评审对 F01–F14、D1–D7、R1–R9 及遗漏项的核查结论与修订点。

| 编号 | 原结论 | 评审结论 | 相对决策版的修订要点与代码证据 |
| --- | --- | --- | --- |
| F01 | P0 | 需修改 | `workflow_switch.py:52` 仅判 `completed/pushed`；须排除 `sync/history/`，integration 关联对应 release 完成态。 |
| F02 | P0 | 需修改 | `stage_route.py:62` 在 local 下勾选 `close-out` 后亦直接 `complete`；还须核 finish 记录或源分支已合入。 |
| F03 | P0 | 需修改 | 补漏 `validate_change_schema.py:43`、`audit.py:117-128`（非 against 的 branch 审计）及 `gitflow.py:487`。 |
| F04 | P0 | 通过 | `push_audit.py:33-55,102` 与 `sync_pull.py:38,51-62`、`sync.py:229` 缺陷完全属实。 |
| F05 | P0 | 需修改 | `commands_release.py:284` 只写文件不 commit；保持不隐式提交，在 `publish/pr/integrate` 锁定并校验一致。 |
| F06 | P0 | 需修改 | 除 `review` 外，`catchup_plan.py:145-166` 的 `verify/fact` 也用 `owned_code`，须同步覆盖无 module 代码变更。 |
| F07 | P0 | 需修改 | `attestations.py:141-150` 用可执行文件 `stat` 而非摘要；复制证据后须重写 `detail["report"]["path"]`。 |
| F08 | P0 | 需修改 | `support_line.py:33-54` 补齐首次切出时同步 `latest_release` 至切出 tag 版本，与 Q2 选项 A 绑定。 |
| F09 | P1 | 需修改 | 撤回 R2 误杀：显式字面量路径或空匹配 glob 须写 `<MISSING>` 哨兵，防被 ignore 文件从无到有碰撞旧空集 key。 |
| F10 | P1 | 需修改 | `fact_identity.py:41-63` 须绑定 `rules_sha256`（含 `manifest.rules` 引用文件），tombstone 精确吊销旧 pass。 |
| F11 | P1 | 需修改 | Q1 已裁定：保留 `42b3c0c`，`--yolo` 下 design 由 Agent 裁定，`route` 返回 `ready`。 |
| F12 | P1 | 需修改 | 补漏：support 上热修 `CHANGE.md` 引用仅在 `<trunk>` 的 Bug 时，`validate_records.py:252` 会报 `record_missing`。 |
| F13 | P1 | 通过 | `publish.py:108-112` 已接受包含 `before` 与 `release_head` 的冲突解决提交；补错误指引、文档与 E2E 即可。 |
| F14 | P1 | 需修改 | `code-review.md` 已达 499 行（硬上限 500 行），严禁原位追加；若超限须先按主题拆至每篇 ≤350 行。 |
| D1–D7 | 推迟 | 需修改 | D4 局部上调：`sync` 同步本地与远端**共有**的已存在 `support/*` 分支；其余 D1–D3、D5–D7 维持推迟。 |
| R1–R9 | 否决 | 需修改 | R2 改为吸收（并入 F09）；其余 R1、R3–R9（决策版正文误写 R10，统一记 R9）否决理由成立。 |

### 仓库约束合规核查

本节核查方案对 `AGENTS.md` 与 `PROJECT.md` 硬约束的遵守情况。

- **分支开发约束**：本仓直接在 `master` 开发；本 worktree 为既有实验分支，不在其上再开子分支，收口 `--no-ff` 合回 `master`。
- **不引入旧版兼容**：F01 切换 `finish/integrate/` 与 `finish/sync/` 专用路径、F05 删除 `or state["head"]`，均不写旧记录回退分支。
- **不得删除产出物**：维持 R5，support 线切出时不删继承的 `docs/bugs/*`，改用改动门禁与跨 ref 识别。
- **文件与文档规模**：`tests/lint/prose_baseline.txt` 当前为空（0 豁免），所有新增或修改的 Markdown 必须直接满足 `prose.*` 与行数上限。

---

## 2. 分批实施方案（按依赖顺序独立提交）

本节按依赖拓扑将修复拆分为 8 个可独立验证、独立提交的批次。

- pytest 自动落盘 `.test-reports/<UTC>-<pid>/junit.xml`，严禁另挂 `tee`；失败先读 JUnit XML。
- `compileall` 无落盘产物，统一执行：`set -o pipefail; python -m compileall -q skills/mdf/scripts 2>&1 | tee .test-reports/<ts>-build.log`。

### Batch 1：自定义 Trunk 去硬编码与分支分类底座（F03 + F01 分支部分）

本批建立 trunk 感知的分支分类接口，消除全链路 `"master"` 字面量硬编码。

- **涉及文件与函数**：
  - `workspace/gitutil.py`：`branch_details`、`occupies_delivery`（显式交付前缀白名单，排除当前/目标 trunk 与 `support/*`）。
  - `workspace/git_ops.py`（`command_prepare_git`）与 `cli.py`：`prepare-git` 增加 `--trunk`（缺省 `master`）。
  - `workspace/planning.py`（`ensure_planning`、`command_planning_land`）：`"master"` 替换为 `trunk_branch(repo)`。
  - `lifecycle/late_decision.py`、`lifecycle/odr_scope.py`、`lifecycle/odr_acceptance.py`、`lifecycle/pull_finish.py`：替换 `"master"` 字面量。
  - `inspection/validate_change_schema.py`（`validate_change_file`）与 `inspection/audit.py`（`_resolve_base`）：适配动态 trunk。
- **先写的 Failing Tests**：
  - `tests/unit/github_flow/test_workflow_policy.py`：`occupies_delivery` 对 `main`、`trunk`、`production`、`support/1.2` 返回 `False`。
  - `tests/e2e/github_flow/test_workflow_config.py`：`{model: gitflow, trunk: main}` 下 `prepare-git`、`planning`、ODR、PR close-out 全部通过。
- **完成标准**：`rg '"master"' skills/mdf/scripts` 仅余 `DEFAULT_TRUNK`、CLI `--from-master` 参数名与 CI 模板锚点；原 gitflow 用例全绿。
- **验证命令**：`lint`、`build`、`quick`，以及 `python -m pytest tests/e2e/github_flow tests/e2e/planning`。
- **Commit 信息**：`fix(workspace): 清理自定义 trunk 的 master 硬编码并收敛在途分支判定`
- **回滚点与风险**：回滚本批单笔 commit；触及 gitflow 公共路径，以 gitflow 与 planning suite 零回归兜底。

### Batch 2：`workflow switch` 空闲态核验与 `audit-push` / `sync` 适配（F01 + F04 + D4 局部）

本批补齐切换前的嵌套收口记录扫描、全 worktree 干净检查，以及 CI 推送审计与 `sync` 边界。

- **涉及文件与函数**：
  - `lifecycle/release_integration.py`（`record_path`）与 `workspace/sync_pull.py`：改用专用路径 `mdf/finish/integrate/<ver>.json` 与 `mdf/finish/sync/`。
  - `workspace/workflow_switch.py`：`_pending_finish_records` 用 `rglob("*.json")`，跳过 `sync/history/`，integration 核对对应 release 完成态。
  - `workspace/workflow_switch.py`：`require_idle` 遍历 `worktree_map`，核验全部关联 worktree clean 且无 `MERGE_HEAD`。
  - `inspection/push_audit.py`（`classify`、`audit`、`collect`）：从 `before` 读取 workflow，允许审计 `<trunk>` 与 `support/*`。
  - `inspection/push_audit.py`：显式拦截 `support/* -> <trunk>`（`support_merge_forbidden`），github-flow 下关闭 `planning_documents` 与 `maintenance` 直推豁免。
  - `workspace/sync_pull.py`、`workspace/sync.py`、`workspace/workflow_policy.py`：区分 `trunk_pr` / `dev_pr`；仅 gitflow `develop` 允许 `trivial_commits` 免 PR。
  - `workspace/workflow_policy.py`（`sync_trunks`）：github-flow `sync` 一并对齐本地与远端共有的 `support/*` 分支。
- **先写的 Failing Tests**：
  - `tests/e2e/github_flow/test_workflow_config.py`：嵌套 `finish/release/1.2.0.json` 未完成阻断切换、已完成放行；脏关联 worktree 阻断；`main` + `support/1.2` 空闲可切。
  - `tests/e2e/github_flow/test_pr_flow.py`：`trunk: main` 与 `support/1.2` 的 `audit-push`（平台 merge、直推拒绝、`support -> trunk` 违规）。
  - `tests/e2e/github_flow/test_pr_flow.py`：github-flow `sync` 对 trunk 领先返回 `trunk_pr` 且对齐共有 `support/1.2`。
- **完成标准**：空闲态判定无漏检无误杀；`sync` 与 `audit-push` 对 trunk 直推豁免判定完全一致。
- **验证命令**：`lint`、`build`、`quick`，以及 `python -m pytest tests/e2e/github_flow tests/e2e/gitflow/test_sync_pr_smoke.py`。
- **Commit 信息**：`fix(workflow): 补齐切换空闲态递归检查并适配 trunk/support 审计与同步`
- **回滚点与风险**：回滚本批 commit；切换了 `integrate/sync` 状态文件路径，切换前须确认无未完成临时记录。

### Batch 3：固定 `release_head` 持久化与 Local 冲突恢复指引（F05 + F13）

本批锁定 GitHub Flow 发布的 `release_head` 一致性，并补齐 local 冲突恢复闭环。

- **涉及文件与函数**：
  - `lifecycle/commands_release.py` 与 `lifecycle/closeout_commit.py`：保持不隐式 commit，归档时保留并核对 `delivery.json`。
  - `lifecycle/publish.py`、`lifecycle/pull_finish.py`、`lifecycle/pull_publish.py`：首次发布/PR/集成时锁定定版 `HEAD` 写入 `release_head`，删除 `or state["head"]`。
  - `lifecycle/release_integration.py`（`command_release_integrate`）：源 `HEAD != release_head` 时，无 PR 则更新记录并 merge 新 `HEAD`，已有 PR 则报 `release_head_changed`。
  - `workspace/gitflow.py`（`_merge`）：local 冲突 abort 时，在 `details` 给出在 `<trunk>` 手工 `merge --no-ff <release_head>` 解冲突后重跑 `finish-gitflow` 的指引。
- **先写的 Failing Tests**：
  - `tests/e2e/github_flow/test_pr_flow.py`：PR 已开后源分支追加提交报 `release_head_changed`；PR 前追加提交自动纳入新 `release_head`。
  - `tests/e2e/github_flow/test_release_lines.py`：local 冻结切点 release 与 trunk 冲突 → 按提示解冲突提交 → 重跑收口 → tag 精确等于 `release_head`。
  - `tests/e2e/gitflow/test_publish.py`：断言 Gitflow 原有 tag 仍指向 merge commit 不变。
- **完成标准**：任何路径下发布 tag 精确等于最终通过验收的 `release_head`；local/PR 冲突恢复均有 E2E 覆盖。
- **验证命令**：`lint`、`build`、`quick`，以及 `python -m pytest tests/e2e/github_flow tests/e2e/closeout tests/e2e/gitflow/test_publish.py`。
- **Commit 信息**：`fix(release): 锁定 release_head 一致性校验并补齐本地冲突恢复指引`
- **回滚点与风险**：回滚本批 commit；绝不改动 Gitflow 下 `tag_commit = current`（merge commit）的既有契约。

### Batch 4：`support/*` 维护线基线、Trunk-First 与跨分支 Bug 真源（F08 + F12）

本批按 Q2 默认选项 A 收紧单线 hotfix 基线，并建立维护线的 Bug 真源保护与跨 ref 校验。

- **涉及文件与函数**：
  - `lifecycle/support_line.py`（`release_lines`、`hotfix_base`）：合并统计 `v*` tag 与已有 `support/*`。
    无 tag 报错提示走 `bugfix`；单线省略 `--support` 时自动解析到唯一 `support/<line>`。
  - `lifecycle/support_line.py`（`ensure_support_branch`）：远端已有同名分支优先追踪；首次从 tag 切出时同步 `workflow/closeout` 并将 `latest_release` 对齐到切出 tag 版本。
  - `lifecycle/support_line.py`（`verify_trunk_first`）：`urgent_support_first` 核验 `refs/heads/<trunk>` 上 Bug 存在且 `open`；在 `publish/pull_finish` 发布前二次核验。
  - `lifecycle/commands_release.py` / `workspace/gitflow.py`：禁止在 `support/*` 及其 `hotfix/*` 上增删改 `docs/bugs/bug-*.md`。
  - `inspection/validate_records.py`（`validate_record_references`）：校验维护线 `CHANGE.md` 时合并识别 `<trunk>` ref 上的 Bug ID，避免误报 `change.record_missing`。
- **先写的 Failing Tests**：
  - `tests/e2e/github_flow/test_release_lines.py`：单线 `v1.2.0` 后 trunk 前进，省略 `--support` 启动 hotfix 自动走 `support/1.2` 且不含未发布提交；无 tag 报错。
  - `tests/unit/github_flow/test_trunk_first.py` & E2E：`<trunk>` Bug 缺失或已 `closed` 时 `urgent_support_first` 被拒；维护线改 `docs/bugs/*` 被拒；跨 ref Bug 校验通过。
- **完成标准**：维护线不夹带未发布 trunk 代码、不篡改活跃 Bug 真源，且 `release-closeout` 全量校验零 error。
- **验证命令**：`lint`、`build`、`quick`，以及 `python -m pytest tests/unit/github_flow tests/e2e/github_flow`。
- **Commit 信息**：`fix(hotfix): 收紧 github-flow 维护线基线、Trunk-First 核验与 Bug 真源门禁`
- **回滚点与风险**：回滚本批 commit；若用户对 Q2 选 B，则跳过 `hotfix_base` 单线改动，仅提交 F12 门禁。

### Batch 5：`catch-up-plan`、`delivery route` 与 `complete-stage` 闭环（F02 + F06 + F11 + Q1）

本批修复增量规划漏判、PR/local 收尾路由提前完成，以及自动勾选阶段的证据与现场保护。

- **涉及文件与函数**：
  - `lifecycle/catchup_plan.py`（`build_plan`）：凡 `classify(p) == "code"` 且未被忽略的路径（含无 module 根脚本、CI、lockfile）均计入 `review`、`verify`、`fact`。
  - `lifecycle/catchup_plan.py`：`contract = sorted((own_paths | up_paths | set(resolution)) & rule_paths(repo))`。
  - `lifecycle/stage_route.py`（`route`）：保留 `42b3c0c`（Q1 已裁定）：非 yolo 的 design 返回等待态，`--yolo` 由 Agent 裁定。
  - `lifecycle/stage_route.py`（`route`）：`not pending` 时读取 `publish.state_path` 与合并实况，PR mode 依次路由 `pr` → `close-out` → `complete`。
  - `lifecycle/stage_route.py`（`_verify_evidence`）：`branch` 复用 `valid_branch`（核必选 suite），`smart` 要求 `results` 非空且逐项通过。
  - `lifecycle/stage_route.py`（`complete_stage`）：拦截 `MERGE_HEAD`、核验位于 owner worktree、`catch-up` 拒止非材料 dirty 路径，支持中断残留续提。
- **先写的 Failing Tests**：
  - `tests/e2e/delivery/test_catch_up_plan.py`：修改无 module 根脚本、本分支修改 `AGENTS.md` 两条用例，`review/verify/fact` 均不误判 `skip`。
  - `tests/e2e/delivery/test_stage_route.py`：PR mode 五态；非 yolo 的 design 等待审批、`--yolo` 返回 `ready`；缺 suite、空 `results`、`MERGE_HEAD`、残留重试、dirty 代码路径拒绝 `catch-up`。
- **完成标准**：`delivery route`、`complete-stage` 与 `catch-up-plan` 全部边界用例通过，无关 staged 文件零误提。
- **验证命令**：`lint`、`build`、`quick`，以及 `python -m pytest tests/e2e/delivery/test_catch_up_plan.py tests/e2e/delivery/test_stage_route.py`。
- **Commit 信息**：`fix(delivery): 修正 PR 收尾路由、catch-up 漏判并加固 complete-stage 保护`
- **回滚点与风险**：回滚本批 commit；改动集中在 `catchup_plan.py` 与 `stage_route.py`，回归面可控。

### Batch 6：`verify` 内容指纹证据链、并发锁与显式输入覆盖面（F07 + F09 + 吸收 R2）

本批加固 `verify` 凭证的实体校验、跨 worktree 复制、并发防脏写，并补齐 module 级与 gitignored 显式输入。

- **涉及文件与函数**：
  - `execution/modules.py`（`Module`、`_parse_module`）：`Module` 顶层支持可选 `extra_inputs` 与 `external_state`，向下覆盖 `lint`、`build` 与各 suite。
  - `execution/attestations.py`（`explicit_inputs`、`snapshot`）：纳入 module 级字段与 `manifest.rules` 引用文件。
    穿透 `.gitignore` 展开显式 `extra_inputs`（归一化只用 `removeprefix("./")`），空匹配写 `<MISSING>` 哨兵。
  - `execution/attestations.py`（`environment`、`_locked`）：加入 MDF `scripts/` 摘要与工具内容摘要；用 `fcntl.flock` 按 key 串行化核验与写入。
  - `execution/attestations.py`（`record_result`、`reusable`）：记录证据文件 SHA-256（拒 symlink/越界），命中时校验并复制到当前 worktree 新报告目录，更新 `log` 与 `report.path`。
  - `execution/project_verify.py`（`_run_one`）：持锁执行；运行结束后重算 `fingerprint`，输入未变才写入 `passed` 凭证。
- **先写的 Failing Tests**：
  - `tests/e2e/delivery/test_verify_reuse.py`：空目录/篡改 JUnit miss、删源 worktree 后复制件可用、双进程并发仅实跑 1 次、运行中改文件不写凭证。
  - `tests/e2e/delivery/test_verify_reuse.py`：`.github/**`、gitignored 显式输入从无到有/修改均 miss；module 级字段生效；只改 `delivery.json` 仍命中。
  - `tests/unit/delivery/test_attestation_cost.py`：含哈希核验与复制的单次命中耗时 `< 2s`。
- **完成标准**：无悬空证据路径、无脏写缓存、显式输入优先级完全符合原计划 B1。
- **验证命令**：`lint`、`build`、`quick`，以及 `python -m pytest tests/e2e/delivery/test_verify_reuse.py`。
- **Commit 信息**：`fix(verify): 补齐凭证证据校验复制、并发锁与 module 级显式输入`
- **回滚点与风险**：回滚本批 commit；监控命中复制开销，确保 smoke 总耗时留在 300s 预算内。

### Batch 7：`code-review` 与 `fact-audit` 凭证加固及 `--force`（F10）

本批补齐审查与事实审阅的失败 tombstone、现场重算防伪造、warning 子集约束与 `fact-audit --force`。

- **涉及文件与函数**：
  - `reviewing/credentials.py`、`reviewing/report.py`：写凭证前从仓库重算 `effective_rules` 与 `code_identity` 核对 `context`；非 `pass` 写 `failed` tombstone。
  - `reviewing/fact_identity.py`、`reviewing/fact_report.py`：纳入 `manifest.rules` 文件，绑定 `rules_sha256` 与 `warning_keys`；非 `pass` 写 `failed` tombstone。
  - `inspection/audit.py`（`_reuse`）与 `cli.py`：仅当当前 warning 集 `<=` 已审 warning 集且未被 tombstone 吊销时复用；`fact-audit` 增加 `--force`。
- **先写的 Failing Tests**：
  - `tests/unit/delivery/test_review_credentials.py` & `tests/e2e/delivery/test_review_prepare.py`：先 `pass` 后 `changes_requested` 不再命中；篡改 `context` 被拒写。
  - `tests/e2e/docs/test_fact_credentials.py`：新增 `audit.uncovered` warning 使旧凭证 miss；失败吊销旧 pass；`fact-audit --against <sha> --force` 返回 `reuse: null`。
- **完成标准**：三类凭证（verify / code-review / fact-audit）均具备 `--force`、环境/规则绑定与失败吊销。
- **验证命令**：`lint`、`build`、`quick`，以及 `python -m pytest tests/e2e/delivery/test_review_prepare.py tests/e2e/docs/test_fact_credentials.py`。
- **Commit 信息**：`fix(review): 补齐审查与事实凭证重算校验、失败吊销及 fact-audit --force`
- **回滚点与风险**：回滚本批 commit；仅影响审查与事实凭证读写，风险低。

### Batch 8：Skill References、CLI 接口文档与入口契约对齐（F14）

本批在代码契约全部冻结后，一次性对齐 Agent 执行指令文档与系统接口文档。

- **涉及文件与拆分策略**：
  - **超限必拆预警**：`code-review.md` 已 499 行（硬上限 500 行），若新增内容须先按主题拆页至每篇 ≤350 行；`mdf-cli-write.md`（427 行）须守住系统主题叶 450 行上限。
  - **C1/C2 对齐**：`deliver.md`（接入 `delivery route` 与 `complete-stage`）、`fact-audit.md`（删 `:116-136` 三组计数协议）。
    同步更新 `close-out.md`（补 F13 冲突恢复与 `<trunk>`）、`README.md`、`GLOSSARY.md`、`SKILL.md`。
  - **GitHub Flow 对齐**：`initialization.md`、`start.md`、`to.md`、`sync.md`、`pr.md`、`pr-close-out.md`、`hotfix-version.md`、`late-decision.md`、`modules.md`。
  - **维护者接口页**：`docs/system/interfaces/mdf-cli-{write,delivery,review,inspect}.md` 对齐最新 CLI 参数与状态语义。
- **先写的测试**：
  - 更新 `tests/lint/test_deliver_contract.py`、`tests/lint/test_workflow_routes.py`、`tests/lint/test_sync_routes.py` 的路由与 CLI 断言。
- **完成标准**：`tests/lint` 全绿（`prose_baseline.txt` 保持为空）；github-flow 入口无指向 `develop` 的无条件指令。
- **验证命令**：`python -m pytest tests/lint`、`build`、`quick`。
- **Commit 信息**：`docs(skill): 对齐 github-flow、内容指纹与确定性路由的 Skill 指令及 CLI 文档`
- **回滚点与风险**：回滚本批纯文档 commit；每改完单页运行 `mdf.py prose-check --repo . --path <file>` 防触发 `prose.*` 或 `size.hard`。

---

## 3. 收口总验收清单

本节规定全部 8 个批次完成后的发布前总验收步骤。

1. **Lint 门禁**：运行 `python -m pytest tests/lint`，读取 `.test-reports/<ts>-<pid>/junit.xml` 确认 0 failure / 0 skipped。
2. **Build 门禁**：运行 `set -o pipefail; python -m compileall -q skills/mdf/scripts 2>&1 | tee .test-reports/<ts>-build.log`，确认退出码为 `0`。
3. **Smoke 预算核验**：运行 `python -m pytest tests/unit tests/e2e -m 'not release_only'`，核对 JUnit 报告总实际耗时 `< 300s`。
4. **Release 干净冷跑总验收**：清理临时缓存后运行 `python -m pytest tests/unit tests/e2e`，完整 JUnit XML 留存 `.test-reports/`。
5. **按覆盖提取结果**：从同一次 `release` JUnit XML 按 `classname` 前缀提取 `quick` 与各涉及 named suite。
   核对 `github_flow`、`gitflow`、`delivery`、`closeout`、`planning`、`docs`、`init`、`objects` 均全绿，不重复运行子集。
6. **主干合入（待用户授权）**：切回 `master` 执行 `git merge --no-ff github-flow-fingerprint-cli`（严禁 rebase 或跨分支 ff-only）。

---

## 4. 仍需用户拍板的事项

本节两个问题均已由用户裁定，按下列结论实施。

1. **Q1（已裁定）**：`--yolo` 下 design 由 Agent 裁定，不再询问用户；保留 `42b3c0c`，批次 8 统一契约表述。
2. **Q2（已裁定）**：采用选项 A。已有发布 tag 时 hotfix 一律走 `support/<major.minor>`，单线自动解析，免传 `--support`。
   - 无任何发布 tag 时报错并提示改走 `bugfix/*`。
   - 理由是版本语义：patch 不得夹带 trunk 上已合入但未发布的功能。


## 5. 收口复核记录（2026-11-14）

本轮按八个批次复核 workflow、发布、路由、凭证及 Skill 操作步骤，并修复下列偏差。

- Gitflow PR 被误写入 `release_head`，造成 tag 错位及返工阻断。冻结逻辑现仅作用于 github-flow。
  首次 smoke 的 20 项 Gitflow 失败均由既有回归测试检出；修复保留原测试断言。
- smart 阶段门禁拒绝 `passed: false`、缺失 exit code 及非零 exit code。
- verify 写凭证前比较完整 fingerprint key，覆盖执行期间的环境变化。
- verify 证据复制失败时重新执行；不再返回旧证据路径并宣称命中。
- fact 凭证必须具备当前规则摘要与 warning 集合，缺失字段视为 miss。
- start、sync、pr、close-out 按 workflow 解析目标；github-flow release 保持冻结切点并使用 integration 分支解冲突。
- 增补报告篡改、双进程并发、源 worktree 删除后的证据复制回归。

### 接受的实现差异与范围

- branch 阶段门禁直接复用 suite 解析与覆盖函数，等价检查当前 branch、scope、通过声明与必需 suite。
  无需强制调用依赖当前交付定位的 `valid_branch` 包装函数。
- catch-up 对代码路径采用保守范围，module ignore 路径可能触发额外检查；接受该范围扩大以避免漏检。
- D1–D3、D5–D7 继续按决策版推迟；D4 的共有 support 分支同步已完成。
- Q1、Q2 沿用已裁定结论。主干合入等待用户确认。

### 最终验证

- smoke 全部 1770 项通过，0 failure、0 error、0 skipped，JUnit 用时 244.508s，满足 300s 预算。
  报告为 `.test-reports/closeout-smoke-final.xml`。
- release 冷跑使用 `--cache-clear`，各测试创建独立临时仓库及凭证目录。
  全部 1841 项通过，0 failure、0 error、0 skipped，用时 303.08s。
  报告为 `.test-reports/closeout-release-final.xml`，named suite 统计见 `.test-reports/20261114-final-suite-summary.log`。
