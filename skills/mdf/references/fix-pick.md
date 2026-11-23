# Pick 已有修复

本流程用于 GitHub Flow。将 trunk 的修复移植到 support hotfix，或将已合入
support 的修复移植到 trunk bugfix。

树形：not-tree。

## 工作流（唯一执行契约）

start 在确认目标时应用「识别来源」。进入 owner 后，由 next 或 deliver 按
objectives 委托下表。进度记录在同一份 objectives。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 读取来源 | 约束 | 核对 owner、冻结的 commit、验收语义与已有移植进度 | delivery.json、objectives、Git diff | 2 | 保留现场，报告缺项 |
| 2 | 移植修复 | 约束 | 复用选定修复、回归测试和必要依赖，处理目标分支差异 | 源与目标的 diff、移植提交或等价证据 | 3 | 保留现场，留在 2 |
| 3 | 完成 pick | 约束 | 核对目标净改动与来源，记录范围并自勾 pick | 已提交的修复、objectives | 返回调用方 | 修正或补齐后重核 |

## 识别来源

在 GitHub Flow 的 bugfix/hotfix start 步骤 2，按 canonical Bug ID 核对另一条线是否
已有修复。读取该 Bug 的交付记录和相关 Git diff。可用 Bug ID 搜索 commit，再核对
实际修复及回归测试。branch 名、commit 标题和 Bug 状态只能提供线索。

| 本次交付 | 合格来源 | 传给 start CLI |
| --- | --- | --- |
| support hotfix | 已进入 workflow.trunk 的同一 Bug 修复 | `--bug <Bug-ID>` |
| trunk bugfix | 已进入 support 维护线的同一 Bug hotfix | `--bug <Bug-ID> --pick-from <support/线>` |

- 有可信修复时使用 pick。没有修复证据时沿用普通开发。已有候选而无法确认范围时，
  先核实候选或澄清，避免重复实施。
- 按依赖顺序逐个传完整 SHA：`--pick-commit <SHA>`。确认文本写清移植范围、
  所需回归测试和目标验收。选择 merge commit 时确认其 parent 与所需 diff。
- 配置 origin 时，核对共享 trunk 或 support 的 tip。若本地缺少该 tip，先 fetch 来源，
  再确认修复与 Bug 证据。support hotfix 收口还会读取本地 trunk；start 前须同步
  已共享的修复和 canonical Bug。
- pick 使用 `needs_design: no`、qa/dev `0,0`，reviewers 沿用本次 roster。
  CLI 固定 pick 清单，替代 design、开发与 converge；后续 lint、code-review、
  verify branch、fact audit 均待完成。
- start 保留目标分支的 `start_commit`。来源 ref、tip SHA、选定 SHA 与 Bug ID
  记录在 `delivery.json` 的 `pick` 字段，后续始终按固定 SHA 取内容。

## 执行与续办

- 在 owner 中先检查 Git 操作和已应用的 commit 或暂存改动。中断后从对应 SHA
  恢复，保留冲突现场，避免重复应用。
- 单一且范围吻合的普通 commit 可用 `git cherry-pick -x <SHA>`。
  混合提交或 merge commit 先确定合适的 parent 与路径，再移植该 diff 中的修复部分。
  冲突时按目标版本适配，保持源修复的可观察语义。实质目标变化时停止并确认范围。
- 移植修复、回归测试及其必要依赖。留在来源线的材料包括 Bug 状态、delivery
  账本与报告、Change、CHANGELOG 和版本数据。目标事实按后续 fact audit 更新。
- 空 patch 或冲突中全部采用目标内容时，核对现有实现和回归测试确已覆盖同一修复，
  才能记录等价并勾 pick。尚未完成的 Git 操作或未提交的修复须先处理。
- objectives 记录源 SHA 对应的本地 commit、必要适配及等价证据，然后自勾 pick 并提交。
  下一阶段为 lint。后续 code-review、verify branch、fact audit 按目标分支执行，
  来源分支的验收报告留在来源线。
- support hotfix 收口在 `fixed` / `trunk_fixes` 中登记同一 Bug，
  以 `backported` 和固定的 trunk 修复 SHA 填写 `source_commit`。trunk bugfix
  按现有规则维护 canonical Bug 和 named suite 选题。
