# Next

## 选择树

```text
┌──────────────────────────────────┐
│ 1 Resolve workflow               │
└────────────────┬─────────────────┘
                 │
                 ├──── Gitflow 交付分支（含角色分支） ────→ 2 Resume
                 ├──── 无在途流程 ────────────────────────→ 3 Delegate
                 ├──── 状态不明 ──────────────────────────→ [多候选则澄清；证据不足则报告阻塞]
                 │
                 ▼ 其余唯一在途
┌──────────────────────────────────┐
│ 2 Resume                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 仅查看或条件不足 ────→ [说明用户下一步操作]
                 ├──── 可以推进 ────────────→ [执行并交接]
                 └──── 执行失败 ────────────→ [按原流程交接]

步骤 3 仅由步骤 1「无在途流程」进入，不是步骤 2 的后续。

┌──────────────────────────────────┐
│ 3 Delegate                       │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 └──── 通过 ─────────→ [结束]
```

步骤 2 结束后不进入 3。步骤 3 由步骤 1「无在途流程」到达，不是步骤 2 的后续。
`$mdf next?` 与 `$mdf next？` 不进入本流程，由选择树路由到 tree。
步骤 1 的澄清是列出候选并询问，不是 `$mdf clarify`。

## 工作流（唯一执行契约）

读取 `references/common.md`。
续办尚未 Git 化的 init/bootstrap/migrate 时读取 `references/initialization.md`；
续办任一交付时读取 `references/delivery-contract.md`；
续办 bugfix/hotfix/release 的 Verify 阶段时读取 `references/deliver.md`「先测后审」。
无在途时读取并执行 `references/tree.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve workflow | 约束 | 按规则判定 | 分支、调用、证据 | 在途 2；无在途 3 | 多候选则问；证据不足则阻塞 |
| 2 | Resume | 约束 | 按原流程推进或说明下一步 | 原步骤、条件、结果 | 查看或不足则说明；可推进则执行 | 按原流程交接 |
| 3 | Delegate | 约束 | 读取并执行 tree | tree 结果 | 结束 | 停止并报告 |

## 术语与数据结构

### 在途流程识别

先按以下顺序判定，命中即停止：

- Gitflow 交付分支（含角色分支）：当前分支为 Gitflow 交付分支，或 `qa/` / `dev/` 角色分支（如 `qa/feature/`）。
  - 此时本次肯定是该交付的步骤，进入续办。
  - 若该交付正由已显式启动的 deliver 协调，续办其未完成内部步骤后返回 deliver。
- 在途推理：其余情况按下方规则识别在途流程。

表步骤 1「在途 2」同时覆盖上述 Gitflow 交付分支（含角色分支）与其余唯一在途。

在途范围包括全部 MDF workflow 及其内部委托：

- 交付主线与 deliver。
- init、bootstrap、migrate、intake、prp review、CodeWiki、clarify、fix、verify-fix 等尚未完成的流程。

结合当前对话的显式调用、已确认范围、待回答问题、失败与交接记录，以及目标现场识别。
已经完成、取消或被用户替代的流程不算在途；draft PRP、open Bug 或待办事项本身不代表流程已启动。

目标与边界：

- 先核对本次目标；Git 仓库解析绝对 `REPO_ROOT` 并识别已有改动。
- 判定 Gitflow 交付分支（含角色分支）时以当前 checkout 分支名为准。
- 续办尚未 Git 化的 init/bootstrap/migrate 时按 `references/initialization.md`
  核对普通目录和父仓库边界。
- clarify 可仅依赖已确认议题，不要求 Git 仓库。
- 不得在识别前统一要求 manifest ready 或 clean。

按需核对 manifest、当前分支、相关 worktree、产物、验证与恢复记录：

- feature 使用 `references/delivery-contract.md`，通过 `delivery status` 查看
  身份、阶段记录和 worktree 路径。
  - 按下一 intent 切到对应已有 worktree，缺树则停止。
- 按原阶段要求检查 gate 是否有效；不能仅凭文件存在或历史 passed 判断阶段完成。
- 不能仅凭 tree CLI 的 in_progress 或当前 checkout 缺少材料断言没有在途流程。
- 非 feature 分支按原有交付语义判断，不套用 feature gate。

委托与候选：

- 同一流程的内部委托先续办未完成的子步骤，再返回调用方。
- 多个独立候选且上下文未指定当前目标时，列出候选并询问用户选择。
- 证据冲突或不足时说明缺项，不猜测流程、初始化类型或阶段，
  也不把无法判定当作无在途而委托 tree。
- 没有统一的 workflow 状态文件；使用已有上下文与产物，不新增状态协议。

### 续办与交接

完整读取所选 intent 及其要求的公共引用，以其编号工作流、前置条件和失败恢复规则为准。

- 先复核已完成步骤的证据，从尚未完成的步骤续办，不重做已验收且仍有效的操作。
- 交付主线的当前 intent 已完成而交付未结束时，可委托下一个阶段。
  - feature 阶段顺序：start → design → [write-tests ∥ implement] → converge → code-review → finish。
  - bugfix/hotfix/release 阶段顺序：开发 → Verify 阶段（`deliver.md`「先测后审」）→ code-review → finish。
    - release 开发：objectives 必须已写明不联调、同 worktree 或跨 worktree。
    - 同 worktree 未收口时先 `$mdf integrate`，不打开消息通道。
    - 跨 worktree 需要且通道未打开时先 `$mdf integrate`。
    - 联调按选定工作线；双端验收且确认不再改代码后才委托 code-review。
    - Verify 阶段不是独立 intent；next 读取 `deliver.md`「先测后审」自行执行，算作一次续办。
  - 测试与实现都未完成时，沿用已有分工；无分工则先 write-tests，再由后续 next 推进 implement。
- 存在仍在运行的执行者时报告其进度或待交接项，不重复执行其工作。
- 缺失或过期证据按原阶段规则原地补验，不跳过 gate。

授权与确认：

- 显式 next 授权在已确认范围内续办所选 intent，或进入交付主线的下一个 intent。
- 原流程的用户确认、输入、权限与验证要求继续适用，已有有效确认无需重复取得。
- next 不代替方案确认、初始化启用确认或原流程要求的 Git 操作授权。
- 用户仅要求查看时保持只读，报告下一步。
- 条件不足时明确说明：
  - 当前流程与步骤、判定证据、阻塞原因。
  - 用户需要回答的问题、补充的材料或执行的命令。

范围与结束：

- 一次 next 只续办一个所选 intent（包含其内部委托），完成后报告实际结果和后续步骤。
- 不自动串联其余主线，不在续办结束后追加树。
- 所选 intent 为在途 deliver 时，其内部持续交付委托按 `references/deliver.md` 执行。
  - 不得将普通 next 自动升级为 deliver。
- 失败保留现场，按原流程交接。
- 无在途时不自动启动 init、start、prp review 或其他工作；只委托 tree。
- `--depth` 仅在委托 tree 时生效，不控制续办步数。
