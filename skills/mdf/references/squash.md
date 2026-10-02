# Squash

`$mdf squash` 在已确认的地板与段界上，用 soft reset 压成一段或多段提交。
只执行，不做「是否建议 / 几段 / 切法」。无 CLI 参数。

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
│ 2 Execute                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [保留现场并停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Verify                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [保留现场并停止]
```

## 工作流（唯一执行契约）

读取 `references/common.md` 与 `references/delivery-contract.md`
「可选历史整理（squash）」的地板规则与禁止项；不读启发式、不定型。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check entry | 约束 | 核交付上下文、门禁与已确认三元组 | 合法计划 | 2 | 停止 |
| 2 | Execute | 约束 | soft reset 后按段界 restore 并 commit | 新提交链 | 3 | 保留现场并停止 |
| 3 | Verify | 约束 | 树与旧 tip 一致且 start_commit 仍祖先 | 空 diff、clean | 结束 | 保留现场并停止 |

`$mdf squash` 执行本流程。独立调用只推进本 intent；close-out 内部委托时完成后返回。

## 术语与数据结构

### 入口与门禁

<a id="s1"></a>

**入口**

- 解析 Git 根；工作区对已跟踪改动须 clean。
- 须在交付分支：读当前交付材料的 `delivery.json`，取 `start_commit`；
  缺失或不是 HEAD 祖先 → 停止。
- 门禁（任一命中则停、不改写；原文见 `delivery-contract.md` 禁止项）：
  - 已推送分支上改写
  - 审查窗未关时改写
  - 目标主线已合入交付分支后再压
  - tip 为他人提交（author 或 committer email ≠ `git config user.email`）

### 三元组

- 三元组 = 地板 hash + 有序段界 tip（末段=HEAD，≥1）+ 一一对应 messages
  （中文 Conventional Commit；含 Bug 段保留完整 Bug ID）。
- 须调用方已确认，或独立调用在本步收集并确认。
- 独立调用：可算地板**候选**；确认前可起草 message。❌ 不得提案段界/切法。
- close-out 委托：只复核已确认三元组；不起草 message、不定型。
- 复核地板（≥交付地板、≥他人抬升）与段界；地板..HEAD 非空；否则停。
- ❌ 无确认三元组不得进步骤 2；步骤 2 不改已确认 message；不定型。
- 验收：门禁通过、三元组已确认且复核合法 → 执行；否则停止、不改写。

### 执行

<a id="s2"></a>

- 只使用步骤 1 已确认的三元组；先记下旧 tip 完整 hash。
- `git reset --soft <地板>`
- 按确认顺序处理每个段界 tip（原历史上的 commit）：
  - `git restore --source=<段界> --staged --worktree .`
  - `git commit`（该段已确认 message）
- 多段 = 1 次 soft reset + N 次按段界树提交；一段时 N=1。
- ❌ 禁止 `git rebase` / `rebase -i` / `git merge --squash`、越过地板、涵盖他人
  commit。
- ❌ 不得改写已确认 message，不得增删段界。
- 各段文件完全不重叠时才可按路径分批；通用流程仍按段界 **tree**。
- 验收：产生 N 个新提交 → 校验。
- 失败：保留现场，报告旧 tip 与当前 HEAD；❌ 不自动 `reset --hard`。

### 校验

<a id="s3"></a>

- `git diff <旧 tip> HEAD` 必须为空。
- `start_commit` 仍为 HEAD 祖先。
- 工作区 clean。
- 验收通过：独立调用结束；close-out 委托则返回调用方。
- 失败：保留现场，报告旧 tip 与当前 HEAD；不自动回滚。
