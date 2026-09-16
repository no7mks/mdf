# PRP Split

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Inspect                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 未切换 ───────→ 1 Inspect
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Design                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 无需拆分 ─────→ [说明并结束]
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 确认拆分输入
┌──────────────────────────────────┐
│ 3 Preview                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 预检失败 ──────→ [停止并报告]
                 ├──── 仅预览 ────────→ [展示并结束]
                 ├──── 未确认写入 ────→ [停止并报告]
                 │
                 ▼ 预检通过且用户确认写入
┌──────────────────────────────────┐
│ 4 Apply                          │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止并报告]
```

## 工作流（唯一执行契约）

读取 `references/object-contract.md` 与 `references/common.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 检查 | 约束 | 运行 doctor 与 planning ensure，切换至 planning | 工作区、in_progress | 2 | 未切换留 1；其他停止 |
| 2 | 拆分 | 约束 | 确认拆分单元与全量 downstream | 确认、覆盖、downstream | 无需拆分结束；否则 3 | 停止并报告 |
| 3 | 预检 | 脚本 | 确认 clean，预检并展示候选 | diff、非预览写入确认 | 仅预览结束；确认写入 4 | 失败或未确认则停止 |
| 4 | 写入 | 脚本 | 去掉 dry-run 并改写全部下游依赖 | 校验、完整变更或恢复 | 结束 | 停止并报告 |

## 术语与数据结构

### 输入与前置条件

`prp-split` CLI（包括 dry-run）操作前要求当前分支为 planning，且 clean worktree；
预览不提交。入口先运行 `doctor --repo "$REPO_ROOT"` 与
`planning ensure --repo "$REPO_ROOT"`，须 `normal_workflows_allowed`，并按
`references/common.md` 的「切换工作区」规则进入 planning 工作区。
未开工以 `list --repo "$REPO_ROOT" --type proposal` 的 `in_progress` 为准，判定与
`prp-review` 相同。
非预览按公共规则整理本次改动；无关改动阻塞操作或相关范围不明时先澄清。
仅 active draft/ready 且没有关联分支或开发材料的 PRP 可拆分；已有实现或终态拒绝。
子项须能独立实现与验收，共同覆盖原范围，不拆成文件/操作任务，也不额外扩张范围。

### 拆分输入与状态结果

在 planning 上一次调用 `make-id --type proposal --repo "$REPO_ROOT" --slug <子一> --slug <子二>`，
用重复 --slug 提供全部子项；从返回的 items 取得连续、唯一的 ID 与 filename。
该调用只读、不预占编号；不得逐个调用后拼装，也不得先写占位对象。
输入 JSON 文件包含 source、children、downstream、rationale。
children 至少两个，每项为 filename、id、depends_on、body；body 为完整 Proposal 正文。
子项 filename slug 须在 active Proposal 与 Bug 中唯一，且不得与对象 ID 同形。
downstream 为全部原下游 PRP ID 到其所需子 PRP ID 列表的映射，包含历史对象。
逐项确认原上游如何分配、下游如何替换，避免机械地全部继承；rationale 记录范围覆盖与用户确认。
运行 `prp-split --repo "$REPO_ROOT" --spec-file <文件> --dry-run` 展示候选；用户确认后去掉 dry-run。
原对象置 replaced、记录 replaced_by；子对象为 draft。预检通过才整体写入，写入失败恢复原文件。
子对象继承原 PRP 的可选 `milestone`；原对象无该字段时子对象也省略，不生成 `null`。
需要调整阶段归属时，在用户确认依据后修订子 PRP；milestone 不参与依赖分配。
已足够小则说明无需拆分，不强制造多个 PRP；各子项经 prp review 后再 start。
