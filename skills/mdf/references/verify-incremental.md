# Verify 增量复测与结果复用

所有 verify variation 共用本契约：失败 case 修复后，只重跑失败 case 和受修复影响的相关 case。
其他已通过且未受影响的结果必须复用，不强制重跑整个 verify task。
树形：not-tree。由父 verify 的 Run/Record 调用，完成后返回父流程。

## 工作流（唯一执行契约）

原 scope、module、suite 与选题定义验收全集；增量复测只改变本轮执行集合。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Inspect | 约束 | 读取原报告与修复 diff，确定失败和影响范围 | 原请求、case 清单、diff | 2 | 缺证据只补相应范围 |
| 2 | Select | 约束 | 区分复测、复用及尚未执行的 case | 选题与复用依据 | 3 | 影响不明则扩大相关范围 |
| 3 | Run | 约束 | 执行所需 case 与受影响检查，保留原始报告 | 命令、退出状态、入口原生证据 | 4 | 测试失败仍进 4 |
| 4 | Combine | 约束 | 合并实跑与复用证据，核对原请求覆盖 | 汇总报告、来源、未通过项 | 返回父流程 | 可修回 1；阻塞返回父流程 |

## 适用范围

本规则不随 scope、调用方或报告形式改变。

- smart、branch、named、suite shortcut、人工 feature 的 smoke 与 adhoc smart 均适用。
- converge、code-review、fix、bug close、incremental-integration 内部的 verify 同样适用。
- quick、smoke、release、具体 named suite、显式选题和 playbook 使用相同复用原则。
- lint、build、coverage 按检查项判断影响；没有 case 粒度的检查只在失败或受影响时重跑该入口。

## 影响范围与选题

Agent 依据修复 diff 和测试依赖判断影响，不以「上一轮通过」单独证明可以复用。

1. 保存原请求、完整失败报告及已执行 case 清单；报告将被覆盖时先保留副本。
2. 读取实现、tests、fixtures、配置、依赖与环境的变化，纳入共享依赖和有状态步骤的影响。
3. 选中全部失败 case、受影响 case、新增 case 及原请求尚未执行或缺少有效证据的 case。
4. 对其余已通过 case 记录未受影响依据与原报告路径；修复再次变化时重新评估。

| 情形 | 执行动作 |
| --- | --- |
| 原失败或受影响 case | 复测；同一 case 中失败 test 的点名复测可用于修复定位 |
| 已通过且未受影响 | 复用原结果，不再次执行 |
| 尚未执行、报告缺失或无法确认结果 | 只补该范围，不视为通过 |
| 共享 fixture、依赖、配置或环境影响不明 | 扩大到依赖它的相关 case；说明依据 |
| runner 无法精确选 case | 使用最小可执行范围；不得因此默认重跑其他入口 |
| 全部 case 均受影响或均无有效证据 | 执行全部 case；这是影响分析结果，不是失败后的固定动作 |

- test/case 身份须带 module、suite、文件及 runner ID，参数化实例需消歧。
- 原命令未完成 collection、提前退出或超时时，不把报告中未出现的 case 当成已通过。
- 验证配置获批变更后更新实际命令基准，核对成员增减，再补测受影响部分。
- 已知 Bug 的移除、恢复仍按 [专门契约](known-bug-tests.md) 核验；不得把豁免项计作通过 case。
- 新会话、commit 变化、报告被子流程覆盖都不自动使全部结果失效；先恢复证据再判断影响。

## 执行与汇总

这是 Agent 工作流的增量执行方式；普通 `mdf.py verify` 仍执行其请求的命令集合，不自动选择失败 case。

- 首轮按父流程运行 CLI；后续用项目 runner 的 case selector 执行增量集合，无需再次调用整个 verify 请求。
- 每次复测保留对应入口的原生证据与完整命令日志；有原生日志则直接读取，否则用 `mdf.py run` 落盘。
- 相同执行条件下，一次复测完整覆盖多个 suite 的相关成员时复用同一证据，不重复运行。
- 不修改原始失败 JUnit、CLI 输出或退出码；增量结果写新报告，不能把复用结果伪装成本轮实跑。

各入口按下表取证；`mdf.py run` 只保存日志，不代替 Core 的检查判定。

| 入口 | 复测证据与执行方式 |
| --- | --- |
| 测试 case、playbook | runner 或 playbook 报告脚本生成的独立 JUnit，及实际退出状态 |
| coverage | 用 `verify coverage` 重跑受影响入口，保留 coverage.json、Core summary.json 与 targets 判定 |
| lint | 用 `verify lint` 重跑受影响入口，保留项目命令和 Core 结构检查结果、summary.json |
| build | 用 `verify build` 或原 build 命令复测，保留实际退出状态与完整日志，不要求 JUnit |

- 非测试入口用现有 CLI 的最小可执行范围；无精确入口选择能力时，只扩大该入口，不重跑整个 verify task。
- 不用裸 coverage/lint 命令退出 0 代替 Core 的阈值或结构判定。

Agent 在父流程的报告位置保存汇总；named 和无默认文件的 smart 将汇总留在本轮报告目录。

| 汇总信息 | 内容 |
| --- | --- |
| 原请求 | scope、branch（适用时）、module、suite、原选题及当前配置命令 |
| 实跑 | case 或检查项身份、实际命令、退出状态、入口原生报告路径与结果 |
| 复用 | case 身份、原 JUnit/检查报告路径、原通过结果、未受影响依据 |
| 影响分析 | 修复改动、选题理由、缺失或未完成范围、适用豁免 |
| 总结 | 原请求全部成员的有效结果、未通过项和整体结论 |

- 汇总保留父报告的 scope、suites 与 results 条目身份，不能用局部 smart 冒充 branch。
- 每个 results 条目的 `command` 表示当前配置的验证请求；增量实跑命令另记，不能声称运行过原完整命令。
- 汇总条目使用 `incremental` 保存实跑、复用与影响依据；`passed` 表示完整成员的综合结果，不表示原完整命令实跑成功。
- `incremental.original` 必须保存首轮实际结果快照，含实际 `command` 与已有退出状态、报告和日志；后续修复保留该快照。
  当前配置命令改变时只更新条目的请求 `command`，不把新命令配到原执行快照上。
- `incremental.runs` 记录复测命令、真实退出状态与原生报告；`reused` 记录复用项、来源和依据，`reason` 说明影响范围。
- 原条目的 `exit_code`、`log`、`report`、`error`、`details` 保留原始执行事实；原本没有退出码时不补造。
- smart 完成判断与 closeout 消费增量条目时读综合 `passed`；原始失败与复测来源须一并保留，不把综合结果渲染为原命令 exit 0。
- 阶段完成与 closeout 均要求每个增量条目 `passed: true` 且原执行命令可追溯；顶层 `all_passed: true` 不能覆盖失败或缺失的单项状态。
- `all_passed` 仅在原请求覆盖完整、全部非豁免成员有效通过且无命令/环境/预算失败时为 true。
- 部分复测耗时不能冒充完整 suite 的预算证据；原预算失败须单独解决并验证，不能靠 case 转绿消除。
- 汇总不更新 clear commit；不把跨轮结果当成 CLI 在当前 commit 完整运行的证据。
- 主链必要的增量 code-review 继续执行；review 再改代码后仍按本契约补测并更新汇总。

## Playbook

一个 playbook 文件是一个 case；修复后复测失败或受影响的文件，并复用其他文件的通过观察。

- 同一 pending 且状态未变时按 [Playbook 执行](verify-playbooks.md) 收录；已有有效观察不重复执行。
- 修复使 pending 失效时保留原目录，不修改旧 HEAD/状态以通过 `--record`。
- 仅为待复测文件建立新的报告目录，写入 `pending.json` 的 suite 与 playbooks 路径、steps 清单。
  该文件供 `playbook_junit.py` 生成增量 JUnit，不作为 Core `verify --record` 的续办凭证。
- 按原手册顺序执行所选文件全部步骤，包含必要前置与清理；用既有报告脚本生成新 JUnit。
- 由父流程按上节汇总增量 JUnit 与未受影响文件的旧证据，不向旧 pending 收录新的业务状态。
- 多 suite 请求逐一核对覆盖；一个 suite 通过不能代替原请求全部通过。
