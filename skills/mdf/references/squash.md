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
- 地板、禁止项、切法与手段由下文「可选历史整理（squash）」规定。
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
- 门禁（任一命中则停、不改写；原文见本页禁止项）：
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
- deliver 委托时上述计划确认遵守其 confidence 策略；自动裁定与用户确认均须记录依据。

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

### 可选历史整理（squash）

close-out 可在**第一次把目标主线合入交付分支**之前建议整理本地历史。
集成方向：feature/bugfix←develop，release/hotfix←master。非强制；用户拒绝则跳过。
deliver 委托时，是否 squash 与执行计划的确认均按其 confidence 策略裁定。

**职责**：调用方决定是否激活（启发式 + 用户确认）。公开 `$mdf squash` 负责地板、
切段定型、message、确认后执行；可用 `--dry-run` 只产出建议。
#### 地板（`reset --soft` 目标）

地板必须是当前 HEAD 的祖先，且不得早于交付地板；区间为地板..HEAD。

- **交付地板**（能允许的最早点；有 converge 时 = converge 起点）：
  - roster ≥1：定位 roster-join 文件在本分支首次引入的 commit。
    命令：`git log --diff-filter=A --format=%H <start_commit>..HEAD --
    changes/unreleased/<slug>/gates/roster-join.json`。
    核对候选 diff 与合流记录；缺失或不唯一则不可压。角色 worktree 须已清理；不得早于该提交。
  - roster `0,0` 且 objectives checklist **含**开发完成项（owner 开发，或
    `needs_design: yes` 下的 write-tests / implement；含 start 跳过预勾）：
    - 在 `start_commit..HEAD` 上找**最晚**一次使**该**项变为 `[x]` 的 commit。
    - 命令：`git log --format=%H <start_commit>..HEAD -- changes/unreleased/<slug>/objectives.md`。
    - 从新到旧核对候选 diff，取第一笔把目标开发项变为 `[x]` 的提交；不取其他步骤最近勾选。
      找不到或歧义 → **不可 squash**（失败/缺失）。
  - roster `0,0` 且 checklist **无**上述开发完成项：交付地板 = `start_commit`。
    若其不是 HEAD 祖先，或 `start_commit..HEAD` 为空 → **不可 squash**。
- **他人抬升**：检查 `start_commit..HEAD`。
  - `author` 或 `committer` email ≠ 当前 `git config user.email` 的 commit 为他人提交。
  - 若存在他人提交，地板抬到其中**最新一笔**；保留该笔，只压其后。
  - tip 本身即他人提交 → 不可 squash。
  - roster merge 落在交付地板之前则不进区间，不必再判「是否本人」。

地板 = 历史上较晚者（交付地板与他人抬升结果取更近 tip 的一侧）。
有 converge 时由 converge 定义地板语义；本小节供 close-out 选用，converge 入口不询问 squash。
#### 是否建议（可选启发式）

无硬门槛。调用方先取得 `$mdf squash` dry-run 计划，再用计划中的地板收集信号，
交 Jev/Agent 定型是否展示（`noul` / `choice`）：

- `git rev-list --count <地板>..HEAD` ≥ 5；或
- `git log --oneline <地板>..HEAD` 含 ≥2 条标题匹配 `wip|fixup|tmp|临时`
  （大小写不敏感）。

- 未达信号也可展示 dry-run 建议。
- 用户拒绝或调用方决定不展示 → 跳过执行。
#### 手段（只允许 soft reset）

公开 `$mdf squash` 承担地板计算、切段定型、message 与执行。Jev/Agent 在 squash 内定型几段与切法
（`noul` / `choice` / `run`），**不写** commit message；主 Agent 撰写中文
Conventional Commit（含 Bug 的段保留完整 Bug ID）。调用方的「是否建议」不在本段。

执行：多段 = 1 次 soft reset + N 次按段界树提交；完成后树须与旧 tip 一致，且
`start_commit` 仍为 HEAD 祖先。`--dry-run` 只展示计划、不改写。

❌ 禁止：`git rebase` / `rebase -i`、`git merge --squash`、越过地板、涵盖他人
commit。
❌ 也禁止：已推送分支上改写、审查窗未关时改写、目标主线已合入交付分支后再压。
仅当各段改动文件完全不重叠时，才可偷懒按路径分批；通用流程仍按段界 **tree**。
