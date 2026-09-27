# 收敛（Converge）

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Dispatch                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 已派
┌──────────────────────────────────┐
│ 2 Join                           │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Verify                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 可修复实现问题 ──────────→ 3 Verify
                 ├──── 需测试修改批准 ──────────→ [主会话确认后 resume 回 3]
                 ├──── 缺 named suite 文档 ─────→ [停止，提示 $mdf write-tests]
                 ├──── 外部阻塞或三轮无进展 ────→ [记录阻塞并停止]
                 │
                 ▼ 所需 suite 通过
┌──────────────────────────────────┐
│ 4 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止并报告]
```

## 工作流（唯一执行契约）

读取 `references/delivery-contract.md`、`references/common.md`；涉及 PRP 时读取 `references/object-contract.md`。
CLI 使用 `python3 "$MDF_ROOT/scripts/mdf.py" delivery <action> --repo "$REPO_ROOT"`。
独立调用只推进当前 intent；deliver 内部委托时完成后返回调用方，由其选择下一阶段。
独立调用与 deliver 委托均由本 intent 启动恰好 1 个 owner subagent 执行步骤 2–4；
当前 Agent 不得代做 Join、Verify 或 Record。不计入 roster，不可配人数。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Dispatch | Subagent | 启动恰好 1 个 owner subagent 执行步骤 2–4 | 已派执行者 | 2 | 停止并报告 |
| 2 | Join | 约束 | 按模式集成或检查 gate，复核设计与续办记录 | 两路 gate、续办检查 | 3 | 停止并报告 |
| 3 | Verify | 约束 | 验证并修实现 | suite、阻塞 | 4 | 可修或待批准回 3；缺 suite 停并提示 `$mdf write-tests`；阻塞停 |
| 4 | Record | 脚本 | 所需 suite 通过后记录 converge gate 并提交 | 全绿证据、gate、提交 | 结束 | 停止并报告 |

## 术语与数据结构

### 执行者

无法提供 subagent 时停止，不降级代做。已有 converge 执行者先等待，不对同一
owner 另开第二个。subagent 将会话根切到 owner。

- 分派前与结束后运行
  `worktree-check --repo <owner绝对路径> --owner <owner绝对路径> --role owner`。
- 任务写入 MDF_ROOT、owner 绝对路径与分支、Git common dir，以及适用的
  `--auto-pilot` / `--yolo`。
- 结束后当前 Agent 再运行 `delivery check --stage converge`；不以完成摘要替代。

需测试修改批准时 subagent 停止并交出未决；当前 Agent 在主会话确认后 resume
同一 subagent，传入 `--test-approval <用户确认与修改理由>`。
`--auto-pilot` / `--yolo` 由 subagent 自裁定并记录批准，不回主会话提问。

### 范围与前置条件

仅在 owner 工作。先读冻结 roster 的 qa/dev strategy，两侧策略可不同。

- `best-of-n`：
  - 同侧 ≥2 时先评审各路：选一个做 base，让该 dev-x / qa-x 参考其余优点并在该树上改完；
    不把各家合进 owner。
  - 然后运行 `delivery integrate`：`n=1` 不传 winner；`n≥2` 传入 `--qa-branch` /
    `--dev-branch` 为 winner；`n=0` 无角色可合。
  - 脚本 no-ff 只合入 winner。
- `partition`：不选 winner、不传 `--qa-branch` / `--dev-branch`；
  脚本按 index 把该侧全部分支 no-ff 合入 owner。
- 同路径 stage gate 冲突保留先合入版本；其余冲突视为分工重叠，保留现场并停止。
- 完成后提交 `gates/integration.json`，再删除全部角色 worktree 和分支（含 `best-of-n` 未入选者）。

续办与清理：

- 续办仍调用同一命令；脚本核对已记录提交是 owner 的祖先，现存角色未改变，随后只清理剩余角色。
- 角色均已清理时同样核验记录，不重建角色、不再次合并。
- ❌ 缺少有效记录却缺角色时停止并报告。
- `stale_integration` 表示现场被其他操作改变，停止。
- 普通清理失败保留记录，排除阻塞后原地重试。

随后运行 `delivery check --stage converge`。

- 使用 `delivery status` 返回的材料目录定位 `gates/converge-blocked.md`；不存在时无需创建。
- 续办从步骤 1 开始，回读已有阻塞记录，对照当前 HEAD、设计与两路 gate 核对变化，
  重新判断解除条件。
  - 旧记录不替代本次检查或验证。

### 验证与阻塞记录

先跑 Core，再跑 named suite：

1. 运行 `delivery verify`；脚本依次执行 lint、build、quick、smoke，suite 超预算即失败。
2. 再以 `suite-run` 执行 design policy `suites` 所列每个 named suite 的文档化入口命令。

- 修复循环可按该页的命令模板点名执行 test case 或 test 定位失败。
- 📌 最终必须 Core 与 named suite 全部通过；未跑 named suite 不得记录全绿。
- 所列 named suite 在 `docs/system/testing/` 无文档：停止并报告，提示
  `$mdf write-tests` 补齐后重新 integrate；角色树若已删除则在 owner 上补测。

修改授权：

| 对象 | 规则 |
| --- | --- |
| 实现 | 可以自动修复 |
| 测试、fixture、快照、预期值、发现/跳过规则和验证配置 | 增删改必须用户确认 |

- 同时出现可修实现与待批准测试时，先取得测试修改批准，再修实现。
- 取得确认后原地审查与重验，记录 `--test-approval <用户确认与修改理由>`；不回退 intent。

不设总轮数上限。出现下列情况时，写入或更新 `gates/converge-blocked.md` 后阻塞停止，不宣称全绿：

- 需要目标/设计决定、凭据或外部条件。
- 同一失败连续三轮无进展。

阻塞记录的内容，状态标为未解决：

- 当前 HEAD。
- 失败项与命令/退出状态（未执行则说明原因）。
- 已尝试方案、阻塞原因。
- 所需决定或外部条件，以及可检查的解除条件。

阻塞记录的写入约束：

- 写后回读并核对字段与 diff。
- 写入失败时保留现场，在会话中报告同样内容和实际路径后停止。
- 该文件独立于 gate JSON，不要求已有 converge gate。
- ❌ 不得为保存失败而调用 `delivery record --stage converge`，也不手工创建或修改 gate JSON。

收尾：

- 所需 suite 通过后，如有阻塞记录，补记解除证据并标为已解决，回读核对后进入步骤 4。
  - 记录更新失败则保留现场并停止，不宣称本阶段完成。
- 运行 `delivery record --stage converge --summary <收敛结果与 named suite 的命令、结果>`；
  如需测试批准，一并传入批准记录。
