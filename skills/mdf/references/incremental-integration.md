# Incremental integration

merge/pr 内部的增量验收流程。先把 target 合回工作分支，有 change 时完成本流程，再实际 merge/pr。

树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Integrate | 脚本 | 执行 incremental-integration，合回最新 target | 固定 base、target、plan | 有 change 2；否则 merge/pr | 解决冲突并提交后续办 |
| 2 | Review | 约束 | incr-cr 审查本轮合入、冲突修复和交互面 | 增量审查结论 | 3 | 修复后续办 2 |
| 3 | Verify | 脚本 | verify smart 验证受影响范围 | 独立增量报告 | 4 | 修复后回 2 |
| 4 | Fact | 约束 | incr-fa 核对并更新受影响事实 | paths 事实审阅与补齐 | 5 | 修复后回 2 |
| 5 | Consolidate | 约束 | 适用时执行 incr-consolidate | 本轮交付材料提交 | 6 | 修订后继续 |
| 6 | Complete | 脚本 | 确认 reviewed-head、验收结论和最新 target | 增量验收记录 | merge/pr | target 前进回 1 |

## 入口与范围

```bash
python3 "$MDF_ROOT/scripts/mdf.py" incremental-integration --repo "$REPO_ROOT"
```

- target 为本工作分支准备合入的目标；PR mode fetch 远端 target，local 使用已确定的本地 target。
- target → 工作分支使用 no-ff merge；冲突保留现场，解决并提交后继续当前步骤。
- 固定合回前已验收状态为 base。未通过的一轮保留同一 base，范围为 `base..HEAD`。
- 已通过后 target 再次前进或 PR 反馈引入修复，开启下一轮增量验收。
- 原 lint、code-review、verify、fact audit 及 consolidate 保持完成状态。
- incremental-integration 属于 merge/pr 内部，主链 objectives 记录 catch-up 与 consolidate 等独立阶段。

## 增量验收

- incr-cr 按 plan 的 review.paths 派 1 名独立 reviewer，审查本轮改动与冲突修复，复核未解决项。
  主 Agent 汇总并复核修复，按 [code-review](code-review.md) 的增量规则追加结论。
- verify smart 按 verify.paths 与 modules 选择目标用例；命令明确传入 `--test`。
  quick 足以覆盖时记录覆盖依据；验证报告写到 `incremental-integration-verification-report.json`。
- incr-fa 按 [fact-audit](fact-audit.md) 的 paths 范围核对实现、事实页和规则影响。
  必要时执行 fact update，追加本轮事实审阅证据并保留原报告。
- Gitflow 包含 incr-consolidate；github-flow feature / bugfix 同样更新本轮交付材料。
- github-flow 已发布 release / hotfix 追加集成验收记录，final tag 的内容保持固定。
- 所有适用检查通过后继续实际 merge/pr；失败与修复都在本轮内部循环。

```bash
python3 "$MDF_ROOT/scripts/mdf.py" verify --repo "$REPO_ROOT" --scope smart \
  --paths <受影响路径> --test "<目标回归命令>" --report-file <独立增量报告路径>
python3 "$MDF_ROOT/scripts/mdf.py" consolidate --repo "$REPO_ROOT" --incremental
python3 "$MDF_ROOT/scripts/mdf.py" incremental-integration --repo "$REPO_ROOT" \
  --complete --reviewed-head <完整SHA> --summary "本轮 incr-cr、verify smart、incr-fa 及适用文档收敛结论"
```

## 增量规划

`incremental-integration-plan --repo <repo> [--base <sha>]` 按 merge 拓扑独立给出 review、verify、fact 动作。
显式 base 优先；当前 merge/pr 已记录基线时使用该基线。无新增影响的检查可按 plan 跳过。

- 上游提交、本分支修复、冲突解决和 module 交互面共同确定检查范围。
- 原 CR、verify、FA 基线报告继续保留，追加本轮证据，验证使用独立报告。
- 禁止退勾已通过的基线步骤，禁止全量重跑 verify branch、全分支 CR 或全量 FA。
