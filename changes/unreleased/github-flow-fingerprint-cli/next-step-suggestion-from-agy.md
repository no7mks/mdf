# `github-flow-fingerprint-cli`（PLAIN）后续演进与融合建议

## 1. 背景与总体原则

经三套候选实现（`github-flow-fingerprint-cli` [`plain`、`b336e40`]、`codex/github-flow-fingerprint-cli` [`e092477`]、`agy/github-flow-fingerprint-cli` [`6384f67`]）交叉评审，确定以 **`plain` 分支为主干保留**，在此基底上定向修补自身缺陷并融合 `codex` 与 `agy` 的局部优势。

选择该路径的核心原因：
- **模块职责与体积最优**：`plain` 新增文件均控制在 48~264 行，远低于 `PROJECT.md` 700 行拆分线，12 笔演进 commit 边界清晰。
- **冷跑性能与测试基线最稳**：同口径 `release` 全量冷跑 `plain` 1803 例全绿（~290s），显著优于 `agy`（1667 例、~884s，慢 3 倍）且用例密度高于 `codex`（1655 例）。
- **不破坏存量 Gitflow 契约**：未像 `agy` 那样篡改 Gitflow 原有 tag 落点，也未像 `codex` 那样将 `delivery.json` 纳入 verify 指纹导致跨交付分支缓存失效。

后续实施须全程遵守本仓铁律：
- 严禁引入旧版兼容、回退或运行时迁移分支（遵守 `AGENTS.md`）。
- 保持当前小模块边界，单个 `.py` 文件不超过 700 行，手写文本不超过 500 行，单行显示宽度不超过 180。

---

## 2. P0：必须优先修复的正确性与安全缺陷

以下 7 项已在 `plain` 源码或独立复现 probe 中确认会导致错误放行、阻塞合法操作或缓存污染，须在合入 `master` 前全部修完。

### P0-1. 修复 PR mode 下 `delivery route` 提前返回 `complete`

- **涉及文件**：`skills/mdf/scripts/mdf_core/lifecycle/stage_route.py`（`route`）
- **原因**：PR mode 下 `gitflow.py` 强制 `objectives.md` 的 checklist 止于 `catch-up` 且不含 `pr` / `close-out`。当前 `stage_route.route` 一旦发现 `not pending` 即直接返回 `{"state": "complete"}`，导致 `catch-up` 勾选后漏掉 `pr` 与合并后 `close-out` 的续办路由（已在独立 probe 中复现）。
- **建议做法**：参照 `codex` 的 `lifecycle/delivery_progress.py`（`route` 第 42~49 行）：
  1. 当 checklist 全部勾选后，读取 `state_path(repo, data["branch"])` 收口状态记录（校验 `source` 一致）。
  2. 仅当 `state.get("completed") is True` 才返回 `complete`。
  3. 否则若 `configured(repo)["mode"] == "pr"` 且尚无 `state.get("merge_commit")`，返回下一阶段 `pr`；已有 `merge_commit` 或处于 `local` mode 时返回 `close-out`；状态按 `yolo` 返回 `ready` 或 `awaiting_decision_confirmation`。

### P0-2. 修复 `workflow switch` 空闲态检查的两处失灵

- **涉及文件**：`skills/mdf/scripts/mdf_core/workspace/workflow_switch.py`、`skills/mdf/scripts/mdf_core/workspace/gitutil.py`
- **原因**：
  1. `_pending_finish_records` 使用扁平 `folder.glob("*.json")`，而真实收口记录位于嵌套子目录 `finish/<kind>/<slug>.json` 或 `finish/hotfix/<slug>/<start>.json`，导致未完成的 PR 收口完全漏检。
  2. `_in_flight_branches` 对所有本地分支调用 `occupies_delivery(name)`，旧逻辑将非 `master`/`develop`/`planning` 的分支一律视为在途交付，导致自定义 `trunk`（如 `main`）和 `support/*` 维护线存在时永远无法执行 `workflow switch`。
- **建议做法**：
  1. 将 `_pending_finish_records` 改为递归扫描 `folder.rglob("*.json")`（排除 `sync/history/` 历史归档记录）。
  2. 参照 `agy` 的 `workspace/gitutil.py`，将 `occupies_delivery` 收敛为显式交付分支前缀白名单（`feature/`、`bugfix/`、`release/`、`on-demand-release/`、`hotfix/`、`adhoc/`、`qa/`、`dev/`、`codex/`），排除当前/目标 `trunk` 与 `support/*`。
  3. 参照 `agy` 的切换前检查，遍历 `worktree_map` 确保仓库所有关联 worktree 均处于 clean 状态后再执行切换。

### P0-3. 清理全链路残留的 `"master"` 硬编码与 `audit-push` / `sync` 盲区

- **涉及文件**：
  - `skills/mdf/scripts/mdf_core/inspection/push_audit.py`
  - `skills/mdf/scripts/mdf_core/workspace/sync_pull.py`、`workspace/sync.py`、`workspace/workflow_policy.py`
  - `skills/mdf/scripts/mdf_core/workspace/planning.py`、`workspace/git_ops.py`、`cli.py`
  - `skills/mdf/scripts/mdf_core/lifecycle/late_decision.py`、`lifecycle/pull_finish.py`、`lifecycle/publish.py`、`lifecycle/pull_publish.py`
- **原因**：
  1. `push_audit.py` 完全未适配新契约，仍硬编码 `branch not in {"master", "develop"}`；在 `trunk: main` 或 `support/*` 上跑 CI `audit-push` 会直接报 `invalid_audit_target`，且缺少对 `support/* -> trunk` 合并的审计拦截。
  2. `sync_pull.py` 把 `branch == integration_branch(repo)` 等同于 Gitflow 的 `develop`，导致 GitHub Flow 下 `trunk` 误走 `trivial_commits` 免 PR 放行，且返回 `dev_pr` / `dev_pr_required` 而非 `trunk_pr` / `trunk_pr_required`。
  3. `planning.py`、`late_decision.py`、`pull_finish.py` 在 `gitflow` 分支路径下仍写死 `"master"`，破坏 `workflow: {model: gitflow, trunk: main}` 的合法组合；`prepare-git` 缺少 `--trunk` 参数。
- **建议做法**：
  1. 吸收 `codex` 的 `inspection/push_audit.py`：从 `before` 提交读取 `workflow`，允许审计 `<trunk>` 与 `support/*`，显式判定 `support/* -> <trunk>` 的平台合并为 `violation`（`support_merge_forbidden`），并在 GitHub Flow 下关闭 `planning_documents` / `maintenance` 直推豁免。
  2. 吸收 `codex` 的 `workspace/sync_pull.py`：明确区分 `trunk_pr` 与 `dev_pr`，仅 `develop` 允许 `trivial_commits` 直推；同时吸收 `agy` 的 `sync_trunks`，在 GitHub Flow `sync` 时一并对齐本地与远端共有的 `support/<major.minor>` 分支。
  3. 为 `prepare-git` 增加 `--trunk` 参数，并将 `planning.py`、`late_decision.py`、`pull_finish.py` 等处的硬编码 `"master"` 统一替换为 `trunk_branch(repo)`（同时保留 `--from-master` 等 CLI flag 名称不变，但内部基线取 `trunk_branch(repo)`）。

### P0-4. 修复 GitHub Flow 单版本线 `hotfix` 夹带未发布提交的问题

- **涉及文件**：`skills/mdf/scripts/mdf_core/lifecycle/support_line.py`（`hotfix_base`）
- **原因**：当前 `hotfix_base` 在未传 `--support` 且 `len(lines) <= 1` 时直接返回 `(trunk, None)`。一旦 `v1.0.0` 发布后 `trunk` 已合入未发布的下一版特性提交，从 `trunk` 切 `hotfix` 会把未发布特性一起发进补丁版。
- **建议做法**：参照 `agy` 的保守策略：GitHub Flow 下只要存在已发布版本 tag，`hotfix` 一律基于对应版本线的 `support/<major.minor>`（从该次版本最新 `v<major>.<minor>.*` tag 惰性切出，同时统计已有 `support/*` 分支）；当全仓仅有唯一一条已发布次版本线时，允许省略 `--support` 并自动解析到该唯一 `support/<major.minor>`，不再直接从 `trunk` 切出 `hotfix`。

### P0-5. 收紧 `release-integrate` 的 `release_head` 一致性约束，并补齐 Local 模式冲突兜底

- **涉及文件**：`skills/mdf/scripts/mdf_core/lifecycle/release_integration.py`、`skills/mdf/scripts/mdf_core/lifecycle/publish.py`
- **原因**：
  1. `command_release_integrate` 仅检查 `ancestor(record["release_head"], source)` 而非相等；若集成分支建立后 `release/*` 源分支又追加了修复提交，最终 tag 会打在过期的旧 `release_head` 上。
  2. 当前集成分支仅支持 `github-flow + pr`；在 `local` 模式下若冻结切点（`--from-commit`）的 `release/*` 与前进后的 `trunk` 合并冲突，`publish` 直接中止且无法在不污染冻结 `release_head` 的前提下解冲突。
- **建议做法**：
  1. 当 `sha(repo, source) != record["release_head"]` 时明确报错（或显式拒绝继续使用旧集成记录），强制保证发布 tag 所指 `release_head` 与 `release/*` 最终 HEAD 严格一致。
  2. 吸收 `codex`（`lifecycle/release_cutpoint.py`）或 `agy`（`lifecycle/publish.py`）的本地集成机制：`local` 模式下冻结切点合并冲突时同样创建 `codex/integrate/release-<version>` worktree 解冲突，合回 `trunk` 后对原 `release_head` 打 tag 并核验 ancestor 可达性。

### P0-6. 修复 `catch-up-plan` 两处漏判导致的假阳性 `review = skip`

- **涉及文件**：`skills/mdf/scripts/mdf_core/lifecycle/catchup_plan.py`
- **原因**：
  1. `owned_code` 要求 `config.modules_for_paths(repo, [p])` 非空，导致不属于任何 module 的仓库级脚本、CI workflow、根目录配置或 lockfile 在 `base..HEAD` 变化时被 `review` 忽略而误判 `skip`。
  2. `contract = sorted(up_paths & rule_paths(repo))` 仅检查上游并入路径，本分支自身在 `base..HEAD` 修改 `AGENTS.md`、`.mdf/manifest.yaml`、`.mdf/modules.yaml` 时不触发 `rules_or_contract_changed`。
- **建议做法**：
  1. 参照 `agy` 的保守分类：凡 `classify(p) == "code"` 的路径（无论是否归属某个 module，含 `config_paths`）以及工作区未提交的 dirty 非账本路径，均计入触发 `review = focused` 的代码面。
  2. 将 `contract` 扩大为 `sorted((own_paths | up_paths | set(resolution)) & rule_paths(repo))`。

### P0-7. 补齐 Verify 凭证的证据实体校验/复制、并发锁与运行期防脏写

- **涉及文件**：`skills/mdf/scripts/mdf_core/execution/attestations.py`、`skills/mdf/scripts/mdf_core/execution/project_verify.py`
- **原因**：当前 `reusable` 只检查旧报告目录存在且非空未校验（独立 probe 已复现空证据目录仍命中缓存），且直接引用原 worktree 的 `.mdf/reports/...` 路径；一旦原 worktree 删除或 7 天定期清理就会悬空。同时缺少多 worktree 并发写锁、工具自身脚本摘要与运行前后输入一致性复核。
- **建议做法**：保留 `plain` 高效的 `git ls-files -s` 快照算法，融合 `codex` `execution/attestations.py` 的信任链机制：
  1. 写入凭证时记录证据目录内各报告文件的 SHA-256 与权限；复用命中时校验全部文件哈希，并通过 `shutil.copy2` 复制到当前 worktree 新建的 `.mdf/reports/<ts>-<entry>` 目录。
  2. 按 key 加 `fcntl.flock` 文件锁，校验凭证 JSON 自身 checksum 并拒止 symlink。
  3. 环境指纹纳入 MDF `scripts/` 工具代码摘要与关键环境变量白名单（`PYTHONPATH`、`VIRTUAL_ENV` 等）。
  4. 在验证子进程运行结束后重算一次 `input_key`，仅当运行前后 `input_key` 完全一致时才写入通过凭证，防止运行中途改代码污染缓存。

---

## 3. P1：需要吸收的功能闭环与契约文档补强

### P1-1. Review / Fact-audit 凭证的重算校验、失败 Tombstone 与 Warnings 绑定

- **涉及文件**：`skills/mdf/scripts/mdf_core/reviewing/credentials.py`、`reviewing/report.py`、`inspection/audit.py`、`assets/ci/review.py`
- **原因**：
  1. 当前仅 `verify` 实现了失败 tombstone，`code-review`（`changes_requested` / `error`）与 `fact-audit` 失败不会吊销同指纹旧凭证。
  2. `review-report-check` / `fact-audit-report-check` 直接采信传入的 `--context-file` 写凭证，未从当前仓库重算核对，存在过期或伪造 context 写缓存风险。
  3. `fact-audit` 未校验 `audit.warnings`（如 `audit.uncovered`）子集关系；CI 脚本 `assets/ci/review.py` 尚未接入凭证读写与 `--force`。
- **建议做法**：参照 `codex` 的 `reviewing/report.py`、`reviewing/attestation.py` 与 `assets/ci/review.py`：
  1. 写凭证前从仓库现场重算 `identity` / `rules_sha256` 并要求与 `context-file` 一致。
  2. 审阅或核查未通过时写入 `status: "failed"` tombstone，阻断后续同 key 复用。
  3. `fact-audit` 凭证纳入归一化后的 `warnings` 摘要集合，仅当候选凭证的已审阅 warning 覆盖当前 warning 时才允许复用。
  4. 同步升级 `skills/mdf/assets/ci/review.py` 支持 `--force`、命中复用与审查后写凭证。

### P1-2. 扩展 `Module` 顶层与 CLI 级的显式输入 / 外部状态参数

- **涉及文件**：`skills/mdf/scripts/mdf_core/execution/modules.py`、`execution/attestations.py`、`cli.py`
- **原因**：`plain` 仅在 `SuiteEntry` 与 named suite frontmatter 上支持 `extra_inputs` / `external_state`，模块级的 `lint` 与 `build` 无法声明跨目录显式输入或外部状态；CLI 也缺少临时覆盖参数。
- **建议做法**：
  1. 在 `Module` 顶层支持可选 `extra_inputs` 与 `external_state`（向下作用于该 module 的 `lint`、`build` 与各 suite）。
  2. 吸收 `agy` 的缺失显式输入 `<MISSING>` 哨兵与穿透 `.gitignore` 的显式 glob 展开（**注意**：路径归一化必须用 `removeprefix("./")`，切勿照搬 `agy` 的 `lstrip("./")`，后者会把 `.github/**` 截断成 `github/**`）。
  3. 在 `cli.py` 补齐 `verify --extra-inputs`、`verify --external-state` 与 `fact-audit --force`。

### P1-3. 收紧 `support/*` 维护线的 Bug 真源门禁

- **涉及文件**：`skills/mdf/scripts/mdf_core/lifecycle/support_line.py`、`inspection/validate_records.py`、`documents/bugs.py`
- **原因**：契约规定活跃 `Bug` 主记录唯一留在 `<trunk>`，维护线不维护独立 Bug 状态矩阵；`plain` 当前未核验 `urgent_support_first` 对应的 `<trunk>` Bug 是否真实存在且为 `open`，也未拦截在 `support/*` 分支上直接修改 `docs/bugs/*`。
- **建议做法**：吸收 `codex` `lifecycle/support.py` 的门禁：
  1. `ensure_support_branch`：若远端已有 `origin/support/<line>` 优先追踪；首次从 tag 切出时清理继承的未归档 `docs/bugs/bug-*.md`，并把本线 `versioning.latest_release` 对齐到该切出 tag 版本。
  2. `urgent_support_first`：强制核验 `<trunk>` 上存在对应 Bug 且状态为 `open`。
  3. 禁止在 `support/*` 及其 `hotfix/*` 分支上增删改 `docs/bugs/*`；发布前二次核验 Trunk-First；校验 `support/*` 历史 Change 时允许合并识别 `<trunk>` 上的历史 Bug ID。

### P1-4. 加固 `complete-stage` 的 Git 现场保护与异常恢复

- **涉及文件**：`skills/mdf/scripts/mdf_core/lifecycle/stage_route.py`
- **原因**：当仓库存在进行中的 merge/cherry-pick（`MERGE_HEAD` 等）、`verification-report.json` 缺少非空通过 `results` 明细、或上次 `git commit` 因 hook/锁失败而在工作区残留已勾选的 `objectives.md` 时，`complete-stage` 需要更严密的保护与幂等恢复。
- **建议做法**：参照 `codex` `lifecycle/delivery_progress.py`（第 59~151 行）：
  1. 拦截 `git_in_progress_head(repo)` 非空状态，核验当前处于交付 owner worktree。
  2. 校验 `verification-report.json` 的 `results` 列表非空且逐项 `passed is True`，`scope == "branch"` 时复用 `valid_branch` 确认必选 suite 齐全。
  3. 使用 `git commit --only -- <paths>` 严格隔离提交路径，并支持上次提交失败残留 `objectives.md` 勾选/基线行时的恢复重试。

### P1-5. 定向补齐 Skill References 与 README（消除 Gitflow 硬编码指令）

- **涉及文件**：`README.md` 及 `skills/mdf/references/` 下受工作流/自动化直接影响的入口文档
- **原因**：MDF 的 `references/*.md` 直接作为 Agent 执行指令。`plain` 仅更新了 9 份核心文档，外围日常入口仍写死 `master` / `develop` 或残留旧计数播报协议。
- **建议做法**（参照 `codex` 的 C2 文档与 `agy` 的入口契约修订，注意单文件行数 ≤ 500 行且遵守 `doc-structure.md`）：
  1. Workstream C2 对齐：更新 `README.md`、`close-out.md`、`code-review.md`，并清理 `fact-audit.md` 残留的进度计数协议。
  2. Workstream A 入口对齐：定向同步 `initialization.md`（`prepare-git --trunk` 与双模型分支准备）、`start.md`、`sync.md`（`trunk-pr` 委托与 `support/*` 对齐）、`to.md`、`pr-close-out.md`、`hotfix-version.md`、`late-decision.md`、`help.md`，确保 local 模式下 GitHub Flow 规划直接基于 `<trunk>` 的表述前后一致。

### P1-6. 增补跨契约 Lint 守护与新增边界回归测试

- **涉及文件**：`tests/lint/`、`tests/unit/`、`tests/e2e/`
- **原因**：防止 CLI 参数、reference 关键契约词与刚修复的深水区边界在后续迭代中回退。
- **建议做法**：
  1. 参考 `agy` 的 `tests/lint/test_workflow_and_cache_contracts.py` 新增契约 lint 测试（剔除其中 `complete-stage --stage fact` 的错误断言）。
  2. 为本次修补的每一项补齐针对性回归用例：PR mode `catch-up` 完成后路由到 `pr`/`close-out`、嵌套 `finish` 记录拦截 `workflow switch`、`main` + `support/*` 下执行 `workflow switch`、单线 `hotfix` 走 `support/*`、空证据目录拒止缓存命中、运行期修改文件不写缓存、无 module 归属文件触发 `catch-up` 审查、Review/Fact 失败 tombstone 吊销。

---

## 4. 融合时必须规避的反模式（避坑清单）

1. **严禁引入 `codex` 将 `changes/unreleased/<slug>/delivery.json` 纳入 verify 指纹的做法**：会导致不同交付分支即使业务代码完全一致也永远无法命中 verify 凭证。
2. **严禁引入 `codex` 用 `split("/")[0]` 校验保留分支名的写法**：会误杀合法的非保留裸分支名。
3. **严禁引入 `agy` 的 `complete-stage --stage code-review|fact`**：语义审阅与事实核查必须经 `review-report-check` / `fact-audit-report-check` 校验结构化结论，绝不能凭 Markdown 非空自动代勾。
4. **严禁引入 `agy` 对约 50 份无关 `references/*.md` 的泛化改写与超大单文件代码**：避免无关 diff 噪声、文档结构违规与性能退化。
5. **严禁引入 `agy` 修改 Gitflow 原有 tag 位置或允许 Gitflow 使用 `--from-commit` 的改动**：保持存量 Gitflow 行为 100% 不变。
6. **严禁引入 `agy` 的 `state.get("release_head") or state["head"]` 回退分支**：违反本仓不写旧版兼容分支的硬约束。
7. **严禁引入 `agy` 测试间的跨测试模块直接 `import`**：共享测试辅助函数统一放入 `tests/support_github_flow.py`。

---

## 5. 编码前建议先拍板的 2 个设计取舍

1. **`--yolo` 对 `design` 阶段的路由行为**：
   - `plain` 当前在 `--yolo` 时让 `design` 直接返回 `ready`（跳过人工设计审批）；而计划原文与 `codex` 实现均为“`design` 始终返回 `awaiting_design_approval`，`--yolo` 仅自动放行 `pr` / `close-out` 收口确认”。动工前需锁定采用哪一种语义（推荐对齐计划字面语义，仅跳过收口确认）。
2. **GitHub Flow 下尚无任何历史发布 tag 时能否启动 `hotfix`**：
   - 切为“`hotfix` 始终走 `support/<major.minor>`”后，若仓库 `latest_release: none`（尚无任何 `v*` tag），应明确报错提示尚未发布首版、直接走 `bugfix/*` 合入 `<trunk>`。

---

## 6. 最终验收标准

按 `PROJECT.md` 与 `AGENTS.md` 执行完整留痕验证（报告落盘 `.test-reports/`）：
1. `python -m pytest tests/lint`（含文件行数、行宽、package 文件数、`prose_baseline.txt` 与新增契约 lint 全绿）。
2. `python -m compileall -q skills/mdf/scripts`（零编译错误）。
3. 冷跑全量 `python -m pytest tests/unit tests/e2e --junitxml=.test-reports/<ts>-release.xml`（全绿，且总耗时保持在 `plain` 原 ~300s 量级，无性能退化）。
4. 专项核对复用指标：命中凭证时不拉起测试子进程/reviewer，产物完整保留 `original_duration_s`、`check_duration_s`、`reused_from`，且 `--force` 与失败 tombstone 吊销行为符合预期。
