# Next

完整读取 `intents/common.md`、`intents/clarify.md`、
`references/repository-contract.md` 与 `references/object-contract.md`。

`方向`是可选的产品目标、问题或范围提示；它只限定盘点与候选项，不代替用户确认。

## 决策树

```text
doctor → 仓库盘点 → 候选下一步 → 用户确认一个 MVP → clarify
→ 最少 PRP 与依赖 DAG → 用户确认清单 → ID/写 draft → validation
```

## 工作流（唯一执行契约）

1. **脚本**；解析 `REPO_ROOT` 并运行 `doctor`；证据：
   `normal_workflows_allowed: true`；通过 → 2；失败 → manifest 未就绪时提示
   `$mdf init`，其他 findings 报告后停止。
2. **约束**；按可选`方向`盘点 `README.md`、`PROJECT.md`、`JOTS.md`、
   `manifest`、当前事实文档、实现根、测试、active Proposal/Bug、fulfilled Proposal
   与 unreleased Change；追踪候选项所需的仓库证据，但不执行 `audit` 或验证命令，
   也不得把盘点称为审阅；证据：已读范围、未触及范围及理由；通过 → 3；失败 →
   报告缺失材料并停止。
3. **约束**；结合仓库证据与用户目标展示少量候选下一步；每项说明 Problem、目标用户
   或受益方、最小可验证结果、明确排除范围、已有对象重叠及选择理由；仓库证据不能决定
   产品优先级时询问用户；证据：候选项与取舍；通过 → 4；失败 → 继续查证或澄清。
4. **约束**；一次只选择一个 MVP，且必须是最小但可验证、可交付的结果，不得只是
   技术任务清单；证据：用户明确确认该 MVP、目标与边界；通过 → 5；失败 → 回到 3。
5. **约束**；以确认的 MVP 和仓库证据为议题，使用内部 clarify intent；收敛 Problem、
   Desired Outcome、Scope、验收方式、关键取舍、约束与排除范围，并取得 clarify 要求的
   共同理解确认；证据：已解决的决策树；通过 → 6；失败 → 不写入任何对象并停止。
6. **约束**；按独立评审与验证边界拆成最少数量的一个或多个 Proposal，不得为制造
   数量而拆分；每项都满足 Proposal 必填事实。`depends_on` 只记录直接依赖并形成无环
   DAG；fulfilled 依赖视为已满足，其余节点按拓扑批次展示推荐落地顺序，同一批可并行；
   DAG 与批次均为从 `depends_on` 动态计算的会话视图，不写入字段或独立文件；证据：
   PRP 清单、边界、DAG 与批次；通过 → 7；失败 → 回到 5。
7. **约束**；检查 active/fulfilled Proposal 的重叠与复用；已有对象可作为清单项或
   新 Proposal 的直接依赖，但不得由本 intent 修改。需要改变已有对象范围时停止，
   要求先显式调用 `$mdf prp review`；active Bug 只作为风险或阻塞项展示，不写入
   `depends_on`；其他终态 Proposal 不得作为依赖；证据：复用、重复、风险与阻塞判断；
   通过 → 8；失败 → 停止。
8. **约束**；展示每项 Problem、Desired Outcome、In/Out、Acceptance Criteria、
   直接依赖、拓扑批次及现有/新建标记；证据：只有用户明确确认清单才继续；通过 → 9；
   失败 → 回到 5 或 6，不写入任何对象。
9. **脚本**；为每个新 Proposal 提议并确认英文 ASCII kebab-case slug，逐项使用
   `make-id --type proposal --slug` 生成全部 ID 与规范化文件名，再以 Proposal 模板
   写入 `proposals/`；只用 `depends_on` 填入新旧直接依赖，不写入批次，初始状态为
   `draft`；证据：全部 draft；通过 → 10；失败 → 停止并保留现场。
10. **脚本**；所有 draft 写入后运行 `targeted validation`；证据：零 finding；
    通过 → 11；失败 → 保留 draft 和现场并报告 findings，不得宣称产出可落地。
11. **约束**；展示新建与复用 PRP、依赖 DAG、拓扑批次、风险、排除范围和 validation
    结果；证据：会话摘要；通过 → 结束；失败 → 停止。新建对象保持 `draft`，后续逐项
    显式调用 `$mdf prp review` 转为 `ready`；不得自动 commit。
