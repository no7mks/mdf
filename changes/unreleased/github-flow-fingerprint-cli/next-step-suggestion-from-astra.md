# PLAIN 后续工作建议（Astra）

## 定位与基线

- 日期：2026-11-14。
- 整合基底：`github-flow-fingerprint-cli`，HEAD `b336e40`。
- 对照方案：CODEX `e092477`；AGY `6384f67`。
- 共同基线：`master@91a6774`。
- 本文是后续工作建议，不声明修复已经完成，也不替代原始需求与验收。
- 当前文件按用户指定写入 PLAIN worktree；不据此扩大到 merge、发布或清理 worktree。

## 总体建议

保留 PLAIN 的模块边界和细粒度测试，以逐项修复方式融合其他方案。
优先恢复正确性与既有契约，再优化复用效率和文档。

| 来源 | 建议吸收 | 不直接照搬 |
| --- | --- | --- |
| PLAIN | 职责拆分、交互影响面分析、unknown merge 保守处理 | 当前 route、switch 与凭证校验的缺口 |
| CODEX | 执行锁、证据校验与复制、提交隔离、support/CI 校验 | 将交付身份材料默认纳入 verify 指纹 |
| AGY | 显式输入、结构化 release 组合影响、必要契约文档 | Gitflow tag 语义变化、非空报告自动完成语义阶段 |

- 不整分支互相 merge；三套的 CLI、schema、输出字段与凭证格式并不相同。
- 每项先确定唯一契约，再移植实现和测试，不并存两套运行分支。
- 保留原有 Gitflow regression 断言；不得通过修改预期掩盖行为变化。
- 不新增旧版兼容、迁移或旧凭证运行分支。
- 不为缩短代码而省略证据校验，也不为覆盖更多场景而泛化无关功能。

## 证据等级与阅读方法

- **已确认**：Astra 已对照当前源码，或通过独立 probe 复现。
- **待复现**：其他 reviewer 提出，实施前须构建 failing test 或核实调用链。
- **契约待定**：不能仅按某个方案的现状决定，须先核对原始计划与现行规则。
- 下文源码路径均相对 worktree；主要位于 `skills/mdf/scripts/mdf_core/`。
- 优先级表示实施顺序，不等同于线上事故严重等级。

## P0：先完成正确性闭环

### 1. 修正 workflow switch 的空闲态判断

- 状态：已确认。
- 位置：`workspace/workflow_switch.py`。
- 问题：`_pending_finish_records` 只用 `glob("*.json")`。
  实际嵌套的 `finish/<source>/<start>.json` 会漏检。
- 问题：`_in_flight_branches` 未传入 workflow 身份。
  自定义 trunk 与 `support/*` 会被当成在途交付。
- 原因：前者允许在未收口时切换，后者阻止合法切换。
- 建议：递归扫描真实 finish 布局；按当前/目标 trunk 与 branch 类型判断。
  检查相关 worktree 的 dirty 与未结束 Git 操作，不替用户清理现场。
- 参考：AGY 的 trunk-aware 分支分类；CODEX 的递归 finish 扫描。
- 验收：嵌套未完成记录阻断；已完成记录不阻断；自定义 trunk 和 support 不误报。
  真正在途的 feature、role、integration 分支仍阻断；失败前不修改 manifest。

### 2. 修正 delivery route 的 PR 收尾判断

- 状态：已确认。
- 位置：`lifecycle/stage_route.py`。
- 问题：checklist 全勾选便返回 `complete`。
  PR mode 的 checklist 止于 catch-up，不能代表 PR 与 close-out 已完成。
- 原因：自动交付可能在 PR 尚未创建、合并或收尾时提前结束。
- 建议：结合 closeout mode 和 finish 状态，继续路由到 pr 或 close-out。
  只有实际收口完成才返回最终完成状态。
- 参考：CODEX 的 `lifecycle/delivery_progress.py`，保留 PLAIN 输出契约的一致性。
- 验收：覆盖无 PR、等待合并、已合并未收尾、收尾完成及失败恢复五种状态。
  加入“清单全部完成但 finish 尚未完成”的 CLI E2E。

### 3. 加固 verify 凭证的证据链

- 状态：证据目录为空仍可命中已通过 probe 确认；其余保护缺口已对照源码。
- 位置：`execution/attestations.py`、`module_verify.py`、`project_verify.py`。
- 原因：目录存在不能证明原始报告仍完整、通过且对应同一次执行。
  跨 worktree 复用还会受源 worktree 删除与报告清理影响。
- 建议吸收 CODEX 的以下机制：
  - 按 key 加锁，序列化同指纹执行与成功/失败凭证写入。
  - 记录并核验原始证据文件摘要，校验凭证结构与完整性。
  - 命中后复制证据到当前 worktree 的新报告目录，更新引用。
  - 执行前后复核输入 key；运行中输入变化时，不生成可复用成功凭证。
  - 校验路径边界与 symlink，避免凭证路径越界。
- 验收：删除、清空或修改原始报告均 miss；源 worktree 清理不破坏已复制报告。
  并发执行、失败吊销和运行中输入变化均有独立测试。
- 边界：保留 PLAIN 快照思路，但先验证正确性，再评估性能。

### 4. 补齐执行输入声明与失效规则

- 状态：当前能力缺口已对照源码；具体输入集合须按契约冻结。
- 位置：`execution/modules.py`、`execution/attestations.py`、`cli.py`。
- 原因：lint/build 也可能依赖 module 外文件或外部状态。
  仅在 suite 声明这些输入，不能覆盖所有执行入口。
- 建议：补齐 module/CLI 级 `extra_inputs`、`external_state`。
  显式输入优先于默认排除，支持 gitignore 文件与缺失输入哨兵。
- 指纹纳入实际命令、相关配置、工具内容摘要和明确的环境变量白名单。
- 不默认纳入与执行无关的 delivery 身份、进度与生成报告。
  CODEX 当前会选入 `changes/unreleased/<slug>/delivery.json`，会造成额外 miss。
- 不复制 AGY 的 `lstrip("./")`：已确认它会把 `.github/**` 变成 `github/**`。
- 验收：忽略目录内显式输入变化、隐藏目录变化、缺失文件出现均 miss。
  external_state 不复用；等价执行输入跨交付命中；只改交付进度不误失效。
  补充文件 mode、symlink 与 staged/unstaged 状态的边界测试。

### 5. 补齐 GitHub Flow 的 CI 与 sync 边界

- 状态：audit-push 硬编码已确认；sync 放行路径须补 failing test。
- 位置：`inspection/push_audit.py`、`workspace/sync_pull.py`、`workspace/sync.py`。
- 问题：PLAIN 的 audit-push 仍只接受 master/develop。
- 原因：自定义 trunk 与 support 发布无法完成一致的 CI 审计。
- 建议：按 policy ref 的 workflow 识别 trunk/support；补齐 support → trunk 阻断。
  区分 Gitflow develop 的维护放行与 GitHub Flow trunk 的 PR 规则。
  正确返回 trunk-pr/dev-pr 路由，并核对 support sync 的约定范围。
- 参考：CODEX 的 push audit/sync 分类；AGY 的 support sync 处理。
- 验收：覆盖自定义 trunk、support push、平台 merge、直接 push 与缺失证据。
  同时证明原有 Gitflow 允许/拒绝规则未被改变。

### 6. 固定 release 身份并保留 Gitflow 发布语义

- 状态：PLAIN integration 允许源分支继续前进已对照源码；后果须 E2E 复现。
- 位置：`lifecycle/release_integration.py`、`cutpoint.py`、`publish.py`、`pull_publish.py`。
- 原因：固定 release_head 后继续接受新的 release 内容，可能让实际验收内容与 tag 不一致。
- 建议：冻结后源分支变化须明确拒绝或重新走候选确认；不能静默沿用旧 release_head。
  local/PR 两种冲突恢复均应保持发布候选与 integration 结果的身份可核验。
- 参考：CODEX 的冻结身份与 local integration；AGY 的冲突恢复可作为对照。
- 必须保留：Gitflow 原有 tag 指向 merge commit 的契约。
  AGY 将其改成 release head，且修改旧测试断言；该改动不应融合。
- 验收：冻结后追加提交、冲突恢复、trunk 再前进、重试均有明确结果。
  GitHub Flow 与 Gitflow 分别断言 tag 的精确 SHA，不只检查 ancestor。

## P1：补齐审查、维护线与契约

### 7. 加固 review/fact 凭证与 release 组合复用

- 状态：失败吊销和 warning 匹配风险来自其他 reviewer，须逐入口复现。
- 位置：`reviewing/credentials.py`、`report.py`、`fact_report.py`、`fact_identity.py`。
- 原因：一次旧成功不能覆盖后来的失败、新 warning 或变化的需求。
- 建议：记录前重建并核对 context；明确失败吊销的身份范围。
  fact 复用须覆盖当前输入、规则、warnings 和请求范围；保留 `--force`。
- 审查需求摘要归一化 checklist 勾选，但保留正文及关联 Proposal/Bug 的变化。
- release 复用须解释子交付覆盖、直接提交、冲突解决与跨 module 组合影响。
  参考 AGY 的结构化 `combination_impacts`，不按“文件有凭证”直接推导免审。
- 验收：先成功后失败不再命中；新 warning/需求/规则阻止不当复用。
  0 reviewer 仅在净增量与未覆盖组合影响均为空时成立。

### 8. 补齐 catch-up 与 complete-stage 的保护

- 状态：无 module 文件和本分支规则变更漏判风险待 failing test 确认。
- 位置：`lifecycle/catchup_plan.py`、`stage_route.py`、`reviewing/prepare.py`。
- 原因：未归属 module 不等于没有影响；本分支改规则也可能使既有审查失效。
- 建议：明确无 module 代码/配置的保守处理；同时检查本分支和上游规则变化。
  保留 unknown merge 阻止 skip 的行为；明确 dirty 输入的支持或拒绝边界。
- complete-stage 吸收 CODEX 的 HEAD/index 核对、`commit --only` 和重试保护。
  核对 branch/scope/suite/results，拒绝只带 `all_passed` 的空壳证据。
- 不引入 AGY 的“code-review/fact Markdown 非空即可自动完成”。
- review-prepare 可吸收真实代码规模测量，不能只用 numstat 替代结构限制检查。
- 验收：无 module 改动、AGENTS/manifest 变更不错误 skip。
  无关 staged 文件不被提交；commit 失败后可重试；人工工作不被自动勾选。

### 9. 核实 support 线与 Trunk-First 不变量

- 状态：其他 reviewer 的高价值风险，须结合原始计划与端到端行为确认。
- 位置：`lifecycle/support_line.py`、`hotfix_version.py`、close-out 与发布校验入口。
- 原因：仅校验 Bug ID 格式，不能保证 trunk 上存在待修 Bug。
  维护线自身修改 Bug 状态会破坏唯一真源。
- 建议：参考 CODEX 核实 urgent_support_first 对应 Bug 存在且 open。
  在收口及发布前核验 Trunk-First；限制维护线对活跃 Bug 真源的修改。
- 单线 hotfix 是否允许基于带未发布提交的 trunk，先核对发布范围契约。
  不因 AGY 总走 support 就直接照搬，也不默许无关提交进入 patch 发布。
- 验收：不存在/已关闭的 trunk Bug、伪造修复 SHA、维护线修改 Bug 均被识别。
  发布用例精确断言 patch 包含与不包含的提交。
- 限制：不得未经授权删除目标仓库的 `.mdf/` 或 `docs/` 产出物。
  reviewer 提出的删除 Bug 文档方案须先审查边界，不作为通用清理动作。

### 10. 对齐 Skill、CLI 和文档

- 状态：start、initialization、close-out 等说明仍有固定 master/develop 规则，已确认。
- 原因：MDF 的 Skill 文档直接指导 Agent 操作，属于可执行产品契约的一部分。
- 建议：逐页检查 start、initialization、planning、sync、to、pr、close-out、support。
  同步 README、help、GLOSSARY、modules、CLI 参数与实际副作用说明。
- 从 AGY 精选必要修订，并修正其 local planning 文档与实现矛盾。
  不整批复制，也不以修改文件多为由排除必要修订。
- CI reviewer 可吸收 CODEX 的凭证读写与 `--force`，并写明适用范围。
- 验收：文档、CLI help、schema、输出与测试使用同一套术语和状态语义。
  契约 lint 应检查行为约束，不能用字符串存在替代正确性测试。

## 契约取舍先统一

| 事项 | 处理原则 |
| --- | --- |
| yolo 与 design | 核对完整原始计划及 deliver 契约；不能只按一条描述推定 |
| CLI/schema/凭证字段 | 冻结唯一形式，统一调用方、文档和测试 |
| 自动完成阶段 | 限于证据可确定判断的范围，不替代人工工作和语义审阅 |
| tag 与 release_head | 区分 GitHub Flow 新语义和 Gitflow 既有语义 |
| verify 输入集合 | 执行相关性优先；review 的需求身份不能照搬到 verify |

如原始计划已明确上述取舍，直接遵守，不重复请求用户确认。

## 建议实施顺序与交付标准

1. 冻结上述契约；将已确认问题转成小范围 failing tests。
2. 修复 switch、route、CI/sync 和发布身份，保留旧 Gitflow 行为断言。
3. 统一凭证存储与执行机制，再补输入声明、失效和跨 worktree 复用。
4. 复现并修复 review/fact、catch-up、support 的剩余风险。
5. 对齐 Skill 文档，运行针对性验证与完整收口验证。

- 每项先证明缺陷，再修复；避免同时改实现和断言来消除失败。
- 按 PROJECT 要求执行 lint、build、quick；收口跑 smoke，发布前跑 release。
- 完整套件已覆盖的 named suite 不重复运行；从 JUnit 提取结果。
- 每条命令保留完整日志或工具报告，失败先读报告。
- 不因已有测试全绿就关闭独立 probe 发现的问题。
- 不新增无关重构；按职责拆分，不机械按行数拆分。
- 代码硬限制为 1000 行；700 行仅为超限拆分后的限制，不是普遍拆分线。
- 完成前确认：无新增 Gitflow 行为变化、无错误 cache hit、无提前完成交付。

## 本次证据的适用边界

- Astra 同口径运行 lint + unit + 非 release_only E2E：
  AGY 1727、CODEX 1712、PLAIN 1860 项全部通过；三套 build 通过。
- 已读取其他 reviewer 的 release JUnit：
  AGY 1667、CODEX 1655、PLAIN 1803 项全部通过。
- 这些通过结果未覆盖本文所有缺陷；融合后必须重验。
- 不采用“AGY 比其他方案慢三倍”作为性能结论。
  AGY 的 release 在 03:19:15 启动，与 Astra 03:19:28 起的三套并发运行重叠。
  后续 CODEX/PLAIN release 没有这轮竞争，运行条件不等价。
- 若要比较性能，应隔离其他测试负载，固定环境、fixture 与冷/热条件。
  分别测量冷执行、指纹计算、命中核验和跨 worktree 复用，不混成一个总耗时。
