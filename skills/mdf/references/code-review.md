# Code Review

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 三份报告有效且修复续办 ────→ 3 Repair
                 ├──── 失败或缺失 ────────────────→ [停止并报告]
                 │
                 ▼ 新审查或首轮尚未完成
┌──────────────────────────────────┐
│ 2 Review                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 审查未完成 ────→ [停止并报告]
                 │
                 ▼ 三份审查完成
┌──────────────────────────────────┐
│ 3 Repair                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 需要用户决定 ────→ [保留现场并报告]
                 │
                 ▼ 有效问题已解决
┌──────────────────────────────────┐
│ 4 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 重验失败且可修复 ────→ 3 Repair
                 ├──── 通过 ────────────────→ [结束]
                 └──── 其他失败或缺失 ──────→ [停止并报告]
```

## 工作流（唯一执行契约）

读取 `references/common.md`；feature 另读 `references/delivery-contract.md`；
涉及 PRP 或 Bug 时读取 `references/object-contract.md`。
CLI 使用 `python3 "$MDF_ROOT/scripts/mdf.py"`。
独立调用只推进当前 intent；deliver 内部委托时完成后返回调用方，由其选择下一阶段。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 约束 | 核对范围、前置条件及续办证据 | 基线、报告、检查结果 | 修复续办 3；否则 2 | 停止并报告 |
| 2 | 审查 | Subagent | 强制 3 个独立 subagent 各自全量审查 | 三份完整审查 | 3 | 停止并报告 |
| 3 | 修复 | 约束 | 主 Agent 汇总裁定、修复并复核 | 发现、裁定、修复依据 | 4 | 保留现场并报告 |
| 4 | 记录 | 脚本 | 按需重验、保存证据并提交 | 审查记录、验证、提交 | 结束 | 可修复则 3；其他停止 |

## 术语与数据结构

### 范围与前置条件

步骤 1 支持 feature、bugfix、hotfix、release；cwd 为 qa/dev 时切回 owner feature。
先确认目标仓库 ready，读取已有审查记录，识别相关未提交改动并按公共规则提交。
首次审查才固定当前 HEAD 为 review_head；已有同范围修复续办保留原 review_head，不覆盖原报告。
三份首轮报告齐全、基线一致且本次仅为已记录问题的修复续办时，核对前置条件后直接进入 3。
首轮未齐时进入 2 补齐；新的交付改动重新固定 review_head 并进入 2。范围无法判定时停止询问。
不得把未提交改动遗漏在审查范围外；存在无关改动且无法隔离时停止。

| 分支 | 固定基线 |
| --- | --- |
| feature | delivery.json 的 start_commit |
| bugfix、hotfix | start 保存的 `branch.<完整分支名>.mdf-start-commit` |
| release | 上一正式发布版本的 master commit/tag，解析为完整 commit hash |

bugfix/hotfix 用 `git config --local --get "branch.<完整分支名>.mdf-start-commit"` 读取起点。
release 首轮依据正式发布记录确认上一版本，核对其 `v<version>` tag 指向的 commit 位于 master 历史。
不取 master 合回 develop 的合并提交，也不使用移动的 master/develop HEAD 代替发布基线。
首次发布没有上一版本时，须用户明确确认初始基线；基线缺失、歧义或对象不可解析时停止询问。
基线必须是当前 HEAD 的祖先；审查两个端点的内容差异 `git diff <base_commit> <review_head>`，
并读取必要上下文，不能仅按提交标题或文件名审查。release 覆盖上一版本以来的完整变化，
不得仅审 release 分支创建后的改动，也不得因某个 child 已审查而跳过其代码。
步骤 1 仅在新审查时将基线与 review_head 写入草稿，明确尚未通过，再启动审查。
基线写入本次审查记录后固定，续办沿用，不重新追随分支或 tag。

feature 保留前置要求：运行 `delivery status` 定位材料，读取 design 与 converge gate，
核对两者的 `fingerprints.design` 一致；收敛记录缺失、损坏或设计不一致时停止。
运行 `delivery check --stage code-review`；通过则进入 2。
仅返回 `stale_verification` 且同设计已收敛时，记录过期或失败状态，进入 2 补审补验。
其他错误停止，不跳过 converge。bugfix/hotfix/release 不要求 feature 的 design/converge gate；
读取对应 Bug、交付目标、版本材料及适用设计作为审查依据，不为形式创建 feature 材料。

### 三份独立审查

步骤 2 强制启动 3 个独立 subagent。三者收到相同的基线、review_head、工作目录、
目标、验收与适用设计材料，均全量检查正确性、验收覆盖、测试质量、code smell、
架构合理性及非必要复杂度。不安排分工，不按文件、模块或领域拆分，不共享其他审查者结论。
主 Agent 在三份结果全部返回前不修改审查对象；subagent 只读审查，不修改文件或提交。
每份报告列出问题位置、触发条件、影响与证据；无问题也须明确说明完成的范围。
不足 3 个、启动失败、结果缺失或未覆盖全量时，补齐独立审查；无法补齐则停止，不记录通过。
续办只复用同一基线与 review_head 的完整报告；首轮未凑齐三份时不得进入修复或记录完成。

### 汇总、修复与复核

步骤 3 由主 Agent 汇总去重，逐项核实，记录采纳或不采纳的依据；以证据裁定，不按票数决定。
允许自主修复实现，或依据已确认目标/设计纠正、补充、删除错误或重复测试，记录依据。
不得削弱验收或验证门槛；目标/契约变更须用户确认。更好的架构可以建议，超出目标不直接实施。
修复后由主 Agent 复核问题是否解决及是否引入回归，不强制再次启动 3 个 subagent。
同一范围内的修复、复核及重验循环留在步骤 3–4，不重新执行首轮三人审查。
需要用户决定、外部条件或无法继续时报告阻塞，不记录通过的结果。

### 验证与持久证据

步骤 4：feature 先运行 `delivery check --stage code-review`；通过且本轮未改动实现、测试
或验证配置时沿用有效全绿证据；返回 `stale_verification` 或本轮有改动时运行
`delivery verify` 全量重验。其他错误停止。
bugfix/hotfix/release 运行 `project-verify run --repo "$REPO_ROOT"`，
脚本执行 manifest 的全部 `verification.commands`，逐项记录命令与退出状态，
输出并保存 `<完整分支名>.verification.json`（与审查报告同目录）；失败保留失败证据。
finish 使用 `project-verify check --repo "$REPO_ROOT"` 核对输入指纹及全绿结果。
不能用仅检查文档结构的 full validation 代替业务验证。
重验失败且可在既定权限内修复时返回 3，由主 Agent 修复、复核并重验。

四种分支均在 `docs/context/research/code-review/<完整分支名>.md` 保存审查记录，
包含分支、base_commit、初审 review_head、三份独立审查及其身份、逐项裁定、修复与复核、
最终 final_head、验证命令与结果、未解决项。先提交修复，再固定 final_head 并提交审查记录。
无有效未解决问题且验证全绿才可记录完成。feature 另运行
`delivery record --stage code-review --summary <三份审查、裁定、修复与验证依据>` 并提交 gate。
非 feature 以该审查记录为证据，不伪造 feature gate；语义审查由 Agent 负责，CLI 不推理三份结论。

finish 核对记录中的基线、三个审查结果、最终复核及验证均完整，并检查 final_head 到当前 HEAD
是否有实现、测试、验证配置或目标变化；final_head 必须存在且为当前 HEAD 的祖先。
记录文件自身、纯事实与收口文档改动不使实现审查过期，
但事实仍须另审。实现或目标变化后不得沿用通过结论：同次修复续办回到 3；
新交付改动重新从 1 开始。feature 还须通过 CLI 指纹检查。
记录或提交失败时保留现场并报告；不把阶段提交视为审查通过。
