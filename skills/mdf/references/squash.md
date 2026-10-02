# Squash

`$mdf squash [--dry-run]` 在交付分支上整理本地历史：定地板、定型切段、撰写
message，确认后 soft reset 多段提交。是否激活由调用方决定；本 intent 负责怎么压。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check entry                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Plan                           │
└────────────────┬─────────────────┘
                 │
                 ├──── 不可压或失败 ────→ [报告并停止]
                 ├──── --dry-run ───────→ [展示建议并结束]
                 │
                 ▼ 完整调用
┌──────────────────────────────────┐
│ 3 Confirm                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 未确认 ──────→ 3 Confirm
                 ├──── 用户拒绝 ────→ [结束]
                 │
                 ▼ 已确认
┌──────────────────────────────────┐
│ 4 Execute                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留现场并停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 5 Verify                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [保留现场并停止]
```

## 工作流（唯一执行契约）

- 读取 `references/common.md`。
- 读取 `references/delivery-contract.md`「可选历史整理（squash）」：
  地板、禁止项、切法定型与手段。
- 「是否建议」启发式由调用方在 dry-run 计划之上选用；本 intent 不决定是否激活。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check entry | 约束 | 核交付上下文与改写门禁 | 可进入 | 2 | 停止 |
| 2 | Plan | 约束 | 定地板、定型切段、起草 message | 建议计划 | dry-run 结束；否则 3 | 不可压或失败则停 |
| 3 | Confirm | 约束 | 用户确认计划（地板、段界、messages） | 已确认计划 | 4 | 未确认留 3；拒绝结束 |
| 4 | Execute | 脚本 | 调用 squash_execute.py 执行已确认计划 | 退出 0、新提交链、Git trace | 5 | 保留现场并停止 |
| 5 | Verify | 脚本 | 同一计划调用 --verify-only | tree_equal、start_is_ancestor、clean | 结束 | 保留现场并停止 |

`$mdf squash` 执行本流程；`--dry-run` 在步骤 2 后展示建议并结束，不改写。  
独立调用只推进本 intent；close-out 内部委托时完成后返回。

## 术语与数据结构

### 入口与门禁

<a id="s1"></a>

- 解析 Git 根；工作区对已跟踪改动须 clean。
- 须在交付分支：读当前交付材料的 `delivery.json`，取 `start_commit`；
  缺失或不是 HEAD 祖先 → 停止。
- 仅接受可选 `--dry-run`；其它未知 `--` 停止询问。
- 门禁（任一命中则停、不改写；原文见 `delivery-contract.md` 禁止项）：
  - 已推送分支上改写
  - 审查窗未关时改写
  - 目标主线已合入交付分支后再压
  - tip 为他人提交（author 或 committer email ≠ `git config user.email`）

### 计划

<a id="s2"></a>

- 按 contract **地板**规则计算地板（交付地板与他人抬升取较晚者）。
  - 不可压（地板缺失、区间空、tip 他人等）→ 报告原因并停止。
- Jev/Agent 定型**几段与切法**（`noul` / `choice` / `run`，见 `common.md`）；
  **不写** message。
  - 段界 = 有序 tip 列表（均在地板..HEAD；末段 = 当前 HEAD；≥1 段）。
- 主 Agent 撰写每段中文 Conventional Commit message（含 Bug 的段保留完整 Bug ID）。
- 定型或撰写失败 → 报告并停止。
- 产出建议计划：地板 hash、段界 tip、messages、旧 tip。
- 计划 JSON 写入仓外临时文件：`branch`、`start_commit`、`floor`、`old_tip`，
  以及有序 `segments`（每项 `tip`、`message`）；commit 均为完整 hash。
- `--dry-run`：展示建议计划后结束；❌ 不 reset、不 commit。
- 同会话若已有未过期 dry-run 计划且 HEAD 仍为该旧 tip，完整调用可复用，不必重算。

### 确认

<a id="s3"></a>

- 向用户展示建议计划；须明确确认地板、段界与 messages。
- 答复不明 → 留在本步再问；拒绝 → 结束，不改写。
- 修改段界或 message 后须再确认；❌ 不得在未确认下进入执行。
- close-out 委托：用户已对 dry-run 建议确认「执行」时，本步可直接采信该确认。

### 执行

<a id="s4"></a>

- 执行前复核入口门禁与计划确认仍有效；HEAD 已变化则停止，重新计划与确认。
- 通过 Core `run` 调用以下命令，留存完整 JSON 与 Git trace。

  ```bash
  python3 "$MDF_ROOT/scripts/squash_execute.py" --repo "$REPO_ROOT" --plan-file <已确认计划>
  ```
- 脚本核对分支、祖先、段界、身份与远程引用；预检未通过不改写。
- 预检通过后脚本执行一次 `git reset --soft` 与逐段 `git restore --source=`、commit。
- ❌ 禁止 `git rebase` / `rebase -i` / `git merge --squash`、越过地板、涵盖他人
  commit。
- ❌ 不得改写已确认 message，不得增删段界。
- 统一使用脚本按段界 tree 执行，不由 Agent 现场编写同类脚本。
- 失败：保留现场，报告旧 tip 与当前 HEAD；❌ 不自动 `reset --hard`。

### 校验

<a id="s5"></a>

- 使用同一计划，通过 Core `run` 调用上方脚本，追加 `--verify-only`。
- 验收：退出 0；结果 `tree_equal`、`start_is_ancestor`、`clean` 均为 true。
  `clean` 指已跟踪改动干净；未跟踪文件不得与段界路径冲突。
- 验收通过：独立调用结束；close-out 委托则返回调用方。
- 失败：保留现场，报告旧 tip 与当前 HEAD；不自动回滚。
