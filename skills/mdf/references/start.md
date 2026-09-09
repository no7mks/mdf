# Start

一次只启动一个分支。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve branch                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [留在 1 询问]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Start branch                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 创建与推送成功 ────→ [报告并结束]
                 ├──── 创建前检查失败 ────→ [报告 finding，不创建分支]
                 └──── 创建后推送失败 ────→ [保留本地分支，按现场询问]
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/common.md` 与 `references/delivery-contract.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 参数 | 约束 | 确认分支标识；feature 另确认 PRP 与目标 | 参数、依赖、确认目标 | 2 | 留在 1 询问 |
| 2 | 创建 | 脚本 | 运行 start，核对分支创建及推送结果 | 分支、远端、upstream | 结束 | 按失败阶段处理 |

## 术语与数据结构

### 分支参数与创建

<a id="s1"></a>

**参数**

一次只要求一个分支的类型和必要标识：feature/bugfix 要 slug， release/hotfix 要稳定 SemVer。
feature 必须绑定一个 active ready 且依赖满足、未 start 的 PRP。先只读分析并让用户确认
按 `assets/templates/objectives.md` 确认目标、非目标、约束与验收；将确认文本放在仓外临时文件，保持开分支前 clean。

验收：明确参数、PRP 与确认目标。

异常与交接：询问。 不得从自然语言猜测版本。

<a id="s2"></a>

**创建**

解析目标 Git 根为 `REPO_ROOT`；运行 `start --repo "$REPO_ROOT" --kind <kind>`， feature/bugfix 使用
`--name <slug>`；
feature 还须 `--proposal <PRP-ID> --objectives-file <文件>`，
release/hotfix 使用 `--version <semver>`；
CLI 在同一次调用中 fetch， 检查 `origin`、默认
`master`、 来源及 upstream 一致、clean、目标不存在，
再从 develop 创建 feature/bugfix/release 或从 master 创建 hotfix、 推送到 origin 并设置 upstream。

验收：检查、分支、远端与 upstream。

异常与交接：创建前检查失败时不创建分支并报告 finding；创建后推送失败时保留本地分支，报告 CLI 返回的现场，
不自动删分支或重试 start。先核对远端分支与本地 HEAD，再按用户选择补推或处理现场；
基线已推进时先询问用户并建议由 MDF 分析解决。
feature CLI 固定 start_commit，在新分支写入 .specs/<slug>/ 的目标和身份，创建目标提交后推送。
成功后结束，由用户手动触发 design。其他分支不创建新增阶段材料。
