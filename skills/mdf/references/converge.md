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
                 ├──── 需测试修改批准 ────→ [主会话确认后带 --test-approval 重试 2]
                 ├──── 拒绝测试修改 ──────→ [写阻塞记录并停止]
                 ├──── 失败/缺失 ─────────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Verify                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 可修复实现问题 ───────────→ 3 Verify
                 ├──── 仅缺 named suite 文档 ────→ 3 Verify
                 ├──── 需测试修改批准 ───────────→ [主会话确认后 resume 回 3]
                 ├──── 拒绝测试修改 ─────────────→ [写阻塞记录并停止]
                 ├──── 外部阻塞或三轮无进展 ─────→ [记录阻塞并停止]
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
| 2 | Join | 约束 | 集成或检查 gate，复核设计与续办 | 两路 gate、续办 | 3 | 待批准确认后重试 2；拒绝记阻塞停；其他停 |
| 3 | Verify | 约束 | 验证并修实现 | suite、阻塞 | 4 | 可修或待批准回 3；仅缺 suite 文档则补齐回 3；拒绝或阻塞停 |
| 4 | Record | 脚本 | 所需 suite 通过后记录 converge gate 并提交 | 全绿证据、gate、提交 | 结束 | 停止并报告 |

## 术语与数据结构

### 执行者

无法提供 subagent 时停止，不降级代做。已有 converge 执行者先等待，不对同一
owner 另开第二个。subagent 按 `common.md`「切换工作区」绝对路径绑定 owner；
禁止新建 worktree、禁止要求用户切换；禁止 `move_agent_to_root`。
绑定成功后横幅用 owner 的路径与分支；相对上一处变化时打印切换三行。

- 分派前与结束后运行
  `worktree-check --repo <owner绝对路径> --owner <owner绝对路径> --role owner`。
- 任务写入 MDF_ROOT、owner 绝对路径与分支、Git common dir，以及适用的
  `--auto-pilot` / `--yolo`。
- 结束后当前 Agent 再运行 `delivery check --stage code-review`。
  - 它要求 converge gate 与全绿。
  - 确认 `gates/converge.json` 已被 Git 跟踪。
  - 不以完成摘要替代。

需测试修改批准时 subagent 停止并交出未决；当前 Agent 在主会话确认后 resume
同一 subagent，传入 `--test-approval <用户确认与修改理由>`。

- 步骤 2 的 `delivery integrate` 需批准时，以 `delivery integrate --test-approval <记录>` 重试。
- 步骤 3 的修复需批准时，原地续修。
`--auto-pilot` / `--yolo` 由 subagent 自裁定并记录批准，不回主会话提问。
用户拒绝测试修改时，subagent 按「验证与阻塞记录」写入阻塞记录后停止。

### 范围与前置条件

仅在 owner 工作。先读冻结 roster 的 qa/dev strategy，两侧策略可不同。

- `best-of-n`：
  - 同侧 ≥2 时先只读评审各路，选一个做 base（winner），并记下其余各路要吸收的优点及其提交 hash；
    不在角色树上修改，不把各家合进 owner。
  - 然后运行 `delivery integrate`：`n=1` 不传 winner；`n≥2` 传入 `--qa-branch` /
    `--dev-branch` 为 winner；`n=0` 无角色可合。
  - 脚本 no-ff 只合入 winner。
  - 吸收优点在集成后于 owner 上按记录改写；涉及测试的改写属测试修改，按「修改授权」取得批准。
- `partition`：不选 winner、不传 `--qa-branch` / `--dev-branch`；
  脚本按 index 把该侧全部分支 no-ff 合入 owner。
  - qa ≥2 时脚本在合完全部 qa 后把测试 fingerprint 写入 `gates/integration.json`；
    步骤 4 以它而非第一路 write-tests gate 判断测试是否变化。
- 同路径 stage gate 冲突保留先合入版本；其余冲突视为分工重叠，保留现场并停止。
- 合并完成后由脚本提交 `gates/integration.json`，再删除全部角色 worktree 和分支
  （含 `best-of-n` 未入选者）；Agent 不手工提交该记录或清理角色。

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

先跑 Core，再按需选题：

1. 运行 `delivery verify`；脚本依次执行 lint、build、quick、smoke，suite 超预算即失败。
   （写入 `gates/verification.json`；不是 closeout 的 `$mdf verify --level full`。）
2. 再据 design policy `suites` 与改动摘要，由 Agent+Jev 选题跑具体 test/testcase（可 `suite-run`）。

- roster ≥1 的非 feature 同样经 `delivery verify` 只跑到 smoke；release suite 有意留给其后
  deliver 的 Verify 阶段 / closeout full 执行。

- 修复循环可按该页的命令模板点名执行 test case 或 test 定位失败。
- 📌 最终必须 Core 通过；design 声明的 named 须有可追溯选题结果，未选题不得记录全绿。
- 所列 named suite 在 `docs/system/testing/` 无文档时：
  - 仅缺文档、无需改测试：converge 执行者在 owner 的 `docs/system/testing/` 补该 suite 的独立一页。
    写入 summary 并随本阶段提交，然后留在步骤 3。
  - 须改测试（如该 suite 尚无成员）：属测试修改，按下方修改授权取得批准后在 owner 完成，
    记录 `--test-approval`。

修改授权：

| 对象 | 规则 |
| --- | --- |
| 实现 | 可以自动修复 |
| 所列 named suite 在 `docs/system/testing/` 缺失的文档 | 可以自动补齐 |
| 测试、fixture、快照、预期值、发现/跳过规则和验证配置 | 增删改必须用户确认（auto-pilot 自裁定） |

- 同时出现可修实现与待批准测试时，先取得测试修改批准，再修实现。
- 取得确认后原地审查与重验，记录 `--test-approval <用户确认与修改理由>`；不回退 intent。

不设总轮数上限。出现下列情况时，写入或更新 `gates/converge-blocked.md` 后阻塞停止，不宣称全绿：

- 需要目标/设计决定、凭据或外部条件。
- 用户拒绝所需的测试修改。
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
