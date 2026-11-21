# Verify Playbooks

由 verify 步骤 3 在 `verify-pending` 或恢复 pending 时读取；返回 verify 步骤 4。
修复后的 case 选择与跨轮汇总按 [增量验证契约](verify-incremental.md#playbook) 执行。

## 决策树

本图路由 pending 的执行、报告生成与收录。

```text
┌────────────────────────────┐
│ 1 Resolve pending          │
└─────────────┬──────────────┘
              │
              ├──── missing or stale ────→ [保留现场并停止]
              │
              ▼ pass
┌────────────────────────────┐
│ 2 Execute steps            │
└─────────────┬──────────────┘
              │
              ├──── cannot save ────→ [保留现场并停止]
              │
              ▼ observations saved (including failures)
┌────────────────────────────┐
│ 3 Write JUnit              │
└─────────────┬──────────────┘
              │
              ├──── invalid observations ────→ 2 Execute steps
              ├──── write error ─────────────→ [保留现场并停止]
              │
              ▼ pass
┌────────────────────────────┐
│ 4 Record suites            │
└─────────────┬──────────────┘
              │
              ├──── missing or invalid XML ────→ 3 Write JUnit
              ├──── stale or missing state ────→ [保留现场并停止]
              ├──── other error ───────────────→ [保留现场并停止]
              └──── recorded pass or fail ─────→ [返回 verify 步骤 4]
```

## 工作流（唯一执行契约）

按以下编号执行；任何 pending 均不构成通过证据。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve pending | 约束 | 核原请求、各 pending 与 checkout 状态 | scope、suite、报告目录、HEAD | 2 | 保留现场并停止 |
| 2 | Execute steps | 约束 | 执行每份手册，按观察格式保存每步结果 | JSON、观察与命令日志 | 3 | 无法执行记 failed；无法保存则停止 |
| 3 | Write JUnit | 脚本 | 逐手册调用报告脚本 | 退出码 0、XML 路径 | 4 | 输入不完整回 2；写入失败停止 |
| 4 | Record suites | 脚本 | 逐 suite 调用原 scope 的 `verify --record` | 各 suite 结果、summary | 返回 verify 4 | XML 问题回 3；其余错误停止 |

## 术语与数据结构

### Pending 与续办

本节限定可续用的报告及多 suite 请求的完成条件。

- branch 从 `verification-report.json` 的 `pending.report_dir` 定位；named 使用本轮 CLI 返回的每个目录。
- 新会话恢复 named 时，核对原请求的全部 suite 与各目录的 `pending.json`；不能只取最新一个目录。
  - 原请求无法确定时停止并报告缺项，不猜测范围。
- 核对 pending 的 scope、suite、HEAD；branch 还须匹配分支，且除 Core 报告外 worktree 干净。
- named 允许运行前已有改动；创建 pending 后 tracked 状态不得变化，Core 在收录时校验摘要。
- pending 期间不修改或提交 tracked 文件；branch 仅允许 Core 写本交付的 `verification-report.json`。
- HEAD 或受约束状态变化时保留失败证据、停止本轮；回父流程按增量验证契约复测失败和受影响 case，复用其余通过结果。
- 逐份核对观察 JSON 与 XML 的步骤覆盖；缺少观察才执行，已有失败如实保留，不凭 XML 存在判通过。
- 多 suite 请求保留初轮 command 结果及全部 pending 目录；全部收录通过才报告整个请求通过。
  - 任一 suite 失败仍收录其余结果，合并交给 verify 步骤 4；不得仅凭最后一次收录结果返回成功。

### 观察与报告脚本

Agent 判断实际结果；脚本只验证输入结构并生成 XML。

- 每步命令用 `mdf.py run --name <playbook 名>-<步骤 id>` 代跑，保存返回的 log 路径。
- 每份手册的观察保存为报告目录内独立 JSON 文件，文件名按完整 playbook 路径区分。
- JSON 为按 pending 步骤顺序排列的 object 列表，每项字段如下。

| 字段 | 值与证据要求 |
| --- | --- |
| `id` | pending 中的步骤 id；不得漏项或重复 |
| `result` | `passed` 或 `failed`；无法执行、依赖失败或无法判定使用 `failed` |
| `time` | 本步实际用时，非负有限秒数 |
| `observation` | 实际观察、判定依据；未执行时记录原因 |
| `logs` | 本步命令日志路径数组；无命令时可为空，观察须说明证据来源 |

调用内置脚本，禁止现场生成 XML 转换代码：

```bash
python3 "$MDF_ROOT/scripts/playbook_junit.py" \
  --report-dir "$REPORT_DIR" --playbook "$PLAYBOOK_PATH" --results "$RESULTS_JSON"
```

- `REPORT_DIR` 为 pending 的目录；`PLAYBOOK_PATH` 为仓库相对路径；`RESULTS_JSON` 为本手册观察文件。
- 产物为完整 playbook 路径的 SHA-256 命名的 XML；同名手册不冲突，重试覆盖该手册原报告。
- 不把子命令 JUnit 复制到报告目录；不另写相同 testcase 的 XML，避免重复步骤。

### 收录与返回

根据原 scope 调用 Core；保留每次结果与 `summary.json`。

| scope | 命令 |
| --- | --- |
| branch | `mdf.py verify --scope branch --record <report_dir>` |
| named | `mdf.py verify --scope named --suites <单个 suite> --record <report_dir>` |

- `missing_test_report`、XML 格式错误或步骤不对应：按观察修复报告，回步骤 3。
- pending 缺失、损坏、scope/suite/分支或 checkout 不匹配：保留现场并停止，回父流程恢复原请求证据，只补失败、受影响或缺失范围。
- `verify_command_failed`：测试失败已经收录，连同成功结果返回 verify 步骤 4 分诊；本子流程不修业务。
- 其他错误：保留报告与日志并停止，报告实际错误，不宣称通过。
