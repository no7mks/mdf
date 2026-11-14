# PLAIN 后续工作建议（Opus）

## 背景

- 需求来源：`~/Downloads/implementation_plan.md`（GitHub Flow、内容指纹复用、CLI 提速三条 workstream）。
- 比较对象：三个从 `master@91a6774` 分叉的实现。
  - AGY：`agy/github-flow-fingerprint-cli@6384f67`。
  - CODEX：`codex/github-flow-fingerprint-cli@e092477`。
  - PLAIN：`github-flow-fingerprint-cli@b336e40`（本分支）。
- 结论：代码以 PLAIN 为主干；Skill references 以 AGY 的改写为底稿，按 PLAIN 最终契约校正。
- 依据：三方逐项代码审阅、两位外部审阅者意见、同口径冷跑。
  - 三者 lint、build、release 全部通过；PLAIN 用例最多（release 1803 例）。
  - 并发条件下三者耗时相当，耗时不作为取舍依据。

## 为什么以 PLAIN 为主干

- PLAIN 的缺陷主要是"没覆盖到"，可以增量补齐，且每项都有 CODEX 或 AGY 的参考实现。
- AGY 的缺陷是"行为错了"，散在单个 +8539 行 commit 中，需要逐处剥离：
  - 指纹错误复用（`lstrip("./")`、逗号分隔未实现、module 级漏输入）。
  - gitflow 回归（tag 位置改变、gitflow 下放行 `--from-commit`）。
  - complete-stage 代勾 code-review/fact，catch-up 重试重复提交。
- CODEX 把 `delivery.json` 纳入指纹，跨交付分支几乎不命中；测试最少。
- PLAIN 结构最清晰：12 个 commit，`workflow_switch`、`cutpoint`、`support_line`、`release_integration`、
  `stage_route`、`credentials` 职责独立。

## 工作方式

- 在本分支逐项移植，不整分支 merge AGY 或 CODEX。
  - 原因：两者与 PLAIN 的 CLI、schema、凭证结构不同，整体 merge 会引入冲突语义。
- 每项先写 failing test，再修复；有外部复现的项把复现转为测试。
- 每完成一组提交一次（Conventional Commit，中文描述）。
- 完成后按 `PROJECT.md` 跑 lint、build、release，并从同一份 JUnit 提取各 named suite 结果。
- 最终以 `--no-ff` 合入 `master`。

## 待决事项（开工前确认）

- `--yolo` 是否跳过设计确认。
  - 现状：commit `42b3c0c` 让 yolo 跳过 `awaiting_design_approval`。
  - 计划原文：等待点为"设计确认、人工编码勾选、非 yolo 的 pr/close-out"，按字面设计确认始终等待。
  - CODEX 按原文实现。建议回退到原文语义，除非用户另行决定。

## P0：合入 master 前必须完成

### 1. workflow switch 空闲态判定

- 现状：
  - `workflow_switch.py:46` 用 `folder.glob("*.json")`，不递归。
  - finish 记录实际写在 `finish/<source>/<start>.json`，release/feature/hotfix 的未完成记录检测不到。
  - 测试用扁平文件名 `feature-x.json`，掩盖了问题。
  - `_in_flight_branches` 对所有本地分支调用 `occupies_delivery`，自定义 trunk 与 `support/*` 被判为在途。
- 原因：前者会在有未完成发布时放行切换；后者让非 `master`/`main` 的 trunk 无法切换。
- 做法：
  - 改为 `rglob("*.json")`，测试使用真实嵌套路径。
  - 参照 AGY `gitutil.branch_details(trunk=)` 与带前缀白名单的 `occupies_delivery`。
- 验收：嵌套未完成记录阻断切换；trunk 与 `support/*` 不计为在途。

### 2. 硬编码 master/develop

- 现状：
  - `inspection/push_audit.py` 第 33–54 行固定 `master`、`develop`。
    自定义 trunk 或 `support/*` 上执行 `audit-push` 报 `invalid_audit_target`。
  - `workspace/sync_pull.py` 把 trunk 当作 develop：`trivial_commits` 免 PR 放行，返回 `dev_pr` 而非 `trunk_pr`。
  - `planning.py`（gitflow 分支下的 ensure/land）、`late_decision`、`pull_finish` 仍写死 `"master"`。
  - `prepare-git` 没有 `--trunk`。
- 原因：github-flow 下 CI 审计与 sync 不可用，且 trunk 直推可能被误放行。
- 做法：
  - 参照 CODEX `push_audit.classify/audit`：按 `before` 提交读取 workflow；允许审计 trunk 与 `support/*`；
    拦截 `support/* -> trunk`（`support_merge_forbidden`）；github-flow 下关闭 planning/maintenance 直推豁免。
  - 参照 CODEX `sync_pull.plans`：区分 `trunk_pr` 与 `dev_pr`，仅 develop 允许 `trivial_commits`。
  - 参照 AGY `sync_trunks`：sync 同时对齐本地与远端共有的 `support/*`。
  - 其余位置统一改用 `trunk_branch(repo)`；`prepare-git` 增加 `--trunk`。
- 验收：`trunk: main` 与 `support/1.2` 上的 audit-push、sync 各有 e2e。

### 3. PR mode 路由提前完成

- 现状：`stage_route.route` 在 checklist 全勾后直接返回 `state: complete`。
- 原因：README 规定 PR mode 的 checklist 止于 catch-up，pr 与 close-out 按实际状态续办；
  当前实现会让 Agent 在 PR 未合并时就认为交付完成。外部审阅者已复现。
- 做法：checklist 全勾后，PR mode 继续按 PR 与 close-out 的实际状态返回下一步。
- 验收：复现用例转为测试；PR 未合并时返回 pr 阶段，合并后返回 close-out。

### 4. 单线 hotfix 基于 trunk

- 现状：只有一条已发布线且未传 `--support` 时，hotfix 直接基于 trunk。
- 原因：会把 trunk 上尚未发布的提交当成补丁版本发出。
- 做法：参照 AGY `hotfix_version.resolve_support_line`，github-flow 的 hotfix 总是走 `support/<major.minor>`；
  线数统计同时看 tag 与已有 support 分支。
- 验收：单线场景下 hotfix 从 support 线切出，补丁中不含 trunk 未发布提交。

### 5. release_head 过期

- 现状：`release_integration.py:77` 允许 release 分支越过已记录的 `release_head` 继续前进。
- 原因：tag 会打在过期提交上，违反"tag 始终直指固定 release_head"。
- 做法：
  - release 分支 HEAD 与 `release_head` 不一致时报错。
  - 参照 CODEX `release_cutpoint.freeze_release_head`，用独立 commit 把 `release_head` 写入 `delivery.json`。
- 验收：release 前进后执行 integrate 与 publish 均被拒绝。

### 6. catch-up-plan 错误输出 skip

- 现状：
  - `catchup_plan.py` 的 `owned_code` 只统计归属某个 module 的代码，lockfile、CI 配置等改动被忽略。
  - 规则变化只看上游（`contract = up_paths & rule_paths`），本分支自己改规则不阻止 skip。
- 原因：计划要求 `review = skip` 必须满足"审查规则未变"和"未覆盖交互面为空"，以上两处会误判。
- 做法：
  - 参照 AGY `_is_actionable`：不属于任何 module 的文件按可执行改动处理。
  - 规则变化同时检查本分支与上游两侧。
  - 参照 AGY `_dirty_paths`，未提交改动计入计划。
- 验收：新增"非 module 代码改动"和"本分支改 `AGENTS.md`"两个用例，均不输出 skip。

### 7. verify 凭证的证据完整性

- 现状：`attestations.reusable` 只检查证据目录存在，直接引用旧 worktree 的报告路径；
  没有并发锁、JSON 完整性校验和工具摘要。外部审阅者复现了"证据目录为空仍命中"。
- 原因：源 worktree 被清理或篡改后仍复用，结果不可追溯；MDF 升级后会复用旧 JUnit 解析结果。
- 做法：保留 PLAIN 的 `git ls-files -s` blob 快照内核，吸收 CODEX `execution/attestations.py`：
  - 记录证据文件 SHA-256，命中时复制到当前 worktree 新报告目录（`_evidence`、`_reuse`）。
  - 每 key 一把 `flock`（`_locked`）、JSON checksum、拒绝 symlink。
  - 工具可执行内容摘要、环境变量白名单、MDF 工具摘要纳入指纹（`_tool_digest`）。
  - 实跑后重算 key，输入未变才写凭证。
- 验收：证据为空、证据被改、运行中改文件三种情况均 miss；原 worktree 删除后仍可复用复制件。

### 8. 显式输入的覆盖面

- 现状：
  - `extra_inputs`、`external_state` 只支持 suite 级与 named 级，没有 module 级与 CLI 级。
  - 显式输入只取自非 ignore 快照，被 gitignore 的显式输入不参与指纹。
  - 不在 E 中的 `AGENTS.md` 与 manifest 指向的规则文件按纯文档排除。
  - 没有 `verify --extra-inputs`、`verify --external-state`、`fact-audit --force`。
- 原因：计划要求"显式输入优先于生成物排除"；漏输入会导致错误复用。
- 做法：
  - module 级字段参照 CODEX 与 AGY 的 `Module` 解析；CLI flags 参照 CODEX `cli.py`。
  - 参照 AGY `_walk_explicit_glob` 解析被 gitignore 的显式 glob，用 `<MISSING>` 哨兵记录缺失输入。
  - 不要照搬 AGY 的 `lstrip("./")`，改为只去掉前缀 `./`。
- 验收：`.github/**`、被 gitignore 的输入、逗号分隔多输入，各自变更后都失效。

### 9. code-review 与 fact-audit 凭证

- 现状：
  - 只有 verify 有失败吊销；后一次 `changes_requested` 不会作废之前的 pass。
  - `record_code_credential` 直接信任 context-file，不从仓库重新推导。
  - fact 凭证没有 `warnings` 子集校验，未绑定 `rules_sha256`。
  - `prepare.py` 的 `covered_paths` 允许按文件从多条凭证拼凑覆盖。
- 原因：审查结论可能被旧 pass 覆盖；新出现的 `audit.uncovered` warning 会命中旧干净凭证。
- 做法：
  - code-review 与 fact 失败写 tombstone。
  - 参照 CODEX `reviewing/report.py`：记录前重新推导 context 并要求一致。
  - 参照 AGY `review_cache`：fact 超集复用时校验 `warning_keys` 子集。
  - 覆盖只接受单条凭证的超集，不拼凑。
- 验收：pass 后 changes_requested 阻断复用；新增 warning 时 miss。

### 10. support 线 Bug 真源

- 现状：`support_line.py` 在 `urgent_support_first` 时只检查格式，不核实 trunk 上 Bug 为 open；
  support 分支可以修改 `docs/bugs/*`。
- 原因：计划要求活跃 Bug 主记录只留 trunk，`urgent_support_first` 在 trunk 保持 open。
- 做法：参照 CODEX `lifecycle/support.py`：
  - urgent 时核验 trunk 上对应 Bug 存在且为 open。
  - 维护线禁止增删改 `docs/bugs/bug-*.md`（`support_bug_state`）。
  - 首次切出 support 时清理继承的 open Bug 文档并对齐 `latest_release`；远端已有同名分支时优先追踪远端。
  - 发布前再核验一次 Trunk-First。
- 验收：trunk 上 Bug 已 closed 时 urgent 被拒；support 上改 Bug 文档被拒。

### 11. complete-stage 证据校验

- 现状：verify 证据没有核对 `required_suites`。
- 原因：缺少必需 suite 的报告也能自动勾选 verify。
- 做法：参照 CODEX `delivery_progress.py` 核对报告的 branch、scope、suite、results；
  提交前核对 HEAD 未变、没有进行中的 Git 操作；使用 `commit --only -- paths`。
- 验收：缺 suite、HEAD 变化、存在进行中 merge，三种情况均拒绝。

### 12. Skill references 全量对齐

- 现状：`skills/mdf/references/` 中只有 3 份提到 github-flow；
  `start`、`initialization`、`close-out`、`to`、`hotfix-version`、`deliver` 等仍只描述 gitflow。
  README、`close-out.md`、`code-review.md` 未按计划 C2 对齐，`fact-audit.md` 仍残留计数协议。
- 原因：Skill 文档就是 Agent 的执行指令；在 github-flow 仓库中，Agent 会按 gitflow 指令操作。
- 做法：
  - 以 AGY 的 41 份 references 改写为底稿，逐份按 PLAIN 的 CLI 与契约校正。
  - 删掉 AGY 专属语义：complete-stage 代勾 lint/code-review/fact、gitflow 下的 tag 与 `--from-commit` 变化。
  - README、`close-out.md`、`code-review.md` 参照 CODEX 的改写。
  - 删除 `fact-audit.md` 剩余的计数要求。
  - 同步 `GLOSSARY.md`、`SKILL.md`、`help.md`、`modules.md` 的新增字段与术语。
- 验收：prose lint 通过；在 github-flow 下检索 references 不再出现指向 develop 的指令。

## P1：建议完成

- local 模式冻结切点 release 冲突时使用集成 worktree。
  - 原因：当前 `release-integrate` 只支持 PR mode，local 冲突直接中断。
  - 参照：CODEX `release_cutpoint.integration_source(local=True)`、AGY `publish.py` 的 `codex/integrate` worktree。
- CI reviewer 接入凭证读写与 `--force`。
  - 参照：CODEX `skills/mdf/assets/ci/review.py`。
- review-prepare 调用 `measure_code` 实测文件与 package 体积。
  - 参照：AGY `reviewing/prepare.py` 的 `code_size_measurements`。
- release 组合影响结构化输出。
  - 参照：AGY `review_cache.release_review_plan` 的 `combination_impacts`（冲突、直接提交、重叠文件、共享 module、依赖边）。
- 契约 lint。
  - 吸收 AGY `tests/lint/test_workflow_and_cache_contracts.py`，断言按最终契约修正。
  - 共享 fixture 统一放到 `tests/support_github_flow.py`，不跨测试文件 import。
- 读取 workflow 时缓存 `check-ref-format` 结果，避免每次调用都起子进程。

## 明确不吸收

| 来源 | 内容 | 原因 |
| --- | --- | --- |
| AGY | complete-stage 自动完成 code-review、fact、lint | 语义阶段不能凭报告非空代勾；已复现"审查失败"报告被接受 |
| AGY | gitflow 下 tag 改打 release 分支 head | 改变现有 gitflow 用户行为，计划未要求 |
| AGY | gitflow 下允许 `--from-commit` | 偏离 gitflow 语义 |
| AGY | `state.get("release_head") or state["head"]` 回退 | 只服务旧 finish 记录，违反"不引入旧版兼容" |
| AGY | review key 绑定 objectives 原文 | 勾选进度变化就失效 |
| CODEX | 把 `changes/unreleased/<slug>/delivery.json` 等纳入指纹 | 跨交付分支几乎不命中 |
| CODEX | 保留名用 `split("/")[0]` 判断 | 误拒 `feature` 等裸名 |

## 建议顺序

1. 确认待决事项（yolo 与设计确认）。
2. 正确性：P0 第 1–6 项（切换、硬编码、路由、hotfix、release_head、catch-up）。
3. 凭证：P0 第 7–9 项，先修 verify，再修 review 与 fact。
4. 门禁：P0 第 10–11 项。
5. 文档：P0 第 12 项，放在代码稳定之后，避免文档反复改写。
6. P1。
7. 收口：lint、build、冷跑 release；核对 smoke 耗时预算；`--no-ff` 合入 `master`。
