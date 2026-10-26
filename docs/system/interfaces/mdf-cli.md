# MDF 确定性 CLI 参考

`skills/mdf/scripts/mdf.py` 是 MDF intent 调用的确定性 CLI，供 MDF 仓库维护者审阅与测试。
本页给出调用约定与命令总表；各命令的参数和实际效果按类分在
[只读命令](mdf-cli-inspect.md)、[仓库写入命令](mdf-cli-write.md) 与
[交付阶段与验证](mdf-cli-delivery.md) 三页。

它不是安装后交付给最终用户的 Skill 材料，也不是
`$mdf <intent>` 的用户帮助。后者是用户 intent；本文件中的 command
是 intent 在需要确定性操作时调用的内部接口。

## 调用约定

```bash
python3 skills/mdf/scripts/mdf.py <command> [options]
```

- 输出与错误：
  - 成功时命令向 stdout 输出 JSON。
  - 业务规则拒绝时 stderr 最后一行为 JSON 错误，并以非零状态退出。
  - `doctor`、`validate`、`fact-audit` 向 stderr 实时输出检查阶段与阶段用时。
    「检查结束」仅表示阶段执行完毕，是否通过仍以 JSON findings 为准。
  - 开始列出全局阶段清单（doctor 3 阶段、validate 1 阶段、fact-audit 4 阶段）。
    阶段内每行保留当前全局阶段与已完成阶段数，并行子检查也继承该位置；阶段数不代表耗时比例。
  - 契约检查先列检查组总数；文档扫描后报告局部计数组总数（1 组文档汇总 + 每页 1 组 evidence）。
    各页 evidence 总量在读取该页后确定；无法解析的页面明确报告该组跳过。
  - 局部计数组共享稳定编号；doctor/validate 预登记契约检查与文档汇总，fact-audit 另预登记文档结构检查。
    扫描后为逐页 evidence 追加编号，显示组数变化与完整清单；扫描前标为后续分组待扫描。
  - 每条局部计数显示组编号及全局组数汇总：完成、运行、待开始、中断、跳过，并列出运行组编号。
    各状态数量之和等于总组数；运行与待开始之和表示尚未结束的组数，全局阶段不计入局部组数。
  - 事实与 evidence 检查显示已检查数量、总数及当前路径；generated 显示当前检查项。
  - 配置检查后独立检查组并行，事实文档按页并行；fact-audit 的四类文档结构检查也并行。
    每个线程池最多 4 个 worker；进度按实际完成顺序显示，JSON findings 仍按原检查及路径顺序汇总。
  - 长验证（`verify`、`release-closeout`）期间 stderr 可含进度行与子进程原文。
  - 解析失败时取 stderr 最后一行 JSON；失败细节也可读落盘证据中的
    `stdout_tail` / `stderr_tail`。
- 调用日志：
  - 每次调用在主仓库 `.mdf/logs/<时间戳>-<命令>/` 写日志；参数错误也记录。
    内容为 `stdout.log`、`stderr.log` 与 `meta.json`（argv、cwd、退出码、用时）。
  - 尚无 `.mdf/` 时写到 `MDF_LOG_DIR` 或 `~/.mdf/logs/`。
  - 失败 JSON 带 `log` 路径；内部异常先把 traceback 写入 stderr。
  - 每次调用清理 `.mdf/logs/` 与当前仓库 `.mdf/reports/` 中 7 天前的条目。
- suite 预算：
  - suite 命令受预算限时（默认 quick 30、smoke 300 秒，可由 `verification.budgets` 覆盖）。
  - lint、build 与未设预算的 release 不限时。
  - 超出预算按 process group 终止并失败，错误 details 含已捕获的
    `stdout_tail` / `stderr_tail`。
- `--repo` 接受目标仓库路径。
  - 命令会按自身需要检查 Git 根、MDF manifest 或 clean worktree；以下除外：
    `info`、`run`、`make-id --type bug`、`make-jot-id`、`branch --name`、
    `semver-check` 和 `prepare-git`。
  - `run` 只要求 `--repo` 是目录；不要求 Git 根、manifest 或 clean worktree。
  - `prepare-git` 接受普通目录；已是其他仓库内部路径时失败，不嵌套 `git init`。
  - `make-id --type proposal` 需要 Git 根且当前分支为 `planning`。
  - `upgrade`、`integrate`、`to` 与 `sync` 要求 Git 根，不要求 manifest；
    `sync` 另要求占用三大 trunk 的 worktree（及必要时主 worktree）干净。
- 提交：
  - 对象写入类 CLI 本身不创建提交。
  - 外层写入型 intent 允许并鼓励主动本地提交，包括如实标注状态的阶段成果；
    不夹带无关改动，不替代用户确认或验收。
  - 以下命令按各自协议做提交、集成或远端操作：
    - start、delivery roster-join、finish-gitflow、planning。
    - upgrade、`sync` 与 `merge-no-ff`。
- `--dry-run` 只在 `archive`、`prp-split`、`release-closeout` 和
  `upgrade` 中有效。

## 命令表

| 命令 | 类别 | 页面 |
| --- | --- | --- |
| `info` | 版本信息 | [只读命令](mdf-cli-inspect.md) |
| `run` | 代跑任意命令并落盘 | [只读命令](mdf-cli-inspect.md) |
| `project-rules` | 项目阶段 rule 原文加载 | [只读命令](mdf-cli-inspect.md) |
| `audit-push` | trunk push 事后审计 | [PR mode 与 CI reviewer](mdf-cli-review.md) |
| `review-context` | 固定 Git 审查上下文 | [PR mode 与 CI reviewer](mdf-cli-review.md) |
| `review-report-check` | 外部复核报告校验 | [PR mode 与 CI reviewer](mdf-cli-review.md) |
| `doctor` | 仓库状态 | [只读命令](mdf-cli-inspect.md) |
| `prepare-git` | 非 Git 目录初始化为 master | [仓库写入命令](mdf-cli-write.md) |
| `merge-no-ff` | 在当前分支 no-ff 合并指定提交 | [仓库写入命令](mdf-cli-write.md) |
| `init` | 初始化写入 | [仓库写入命令](mdf-cli-write.md) |
| `validate` | 确定性校验 | [只读命令](mdf-cli-inspect.md) |
| `fact-audit-report-check` | 独立事实 report 校验 | [只读命令](mdf-cli-inspect.md) |
| `fact-audit` | 确定性审计与独立 commit context | [只读命令](mdf-cli-inspect.md) |
| `prose-check` | 文档结构硬限制检查 | [只读命令](mdf-cli-inspect.md) |
| `make-id` | 对象 ID | [只读命令](mdf-cli-inspect.md) |
| `make-jot-id` | Jot ID | [只读命令](mdf-cli-inspect.md) |
| `branch` | 分支解析 | [只读命令](mdf-cli-inspect.md) |
| `semver-check` | 版本校验 | [只读命令](mdf-cli-inspect.md) |
| `archive` | 对象归档 | [仓库写入命令](mdf-cli-write.md) |
| `release-closeout` | 版本收口 | [仓库写入命令](mdf-cli-write.md) |
| `start` | 创建分支 | [仓库写入命令](mdf-cli-write.md) |
| `list` | 对象清单 | [只读命令](mdf-cli-inspect.md) |
| `tree` | draft/ready 混态依赖视图 | [交付阶段与验证](mdf-cli-delivery.md) |
| `prp-split` | 未开工 PRP 拆分 | [交付阶段与验证](mdf-cli-delivery.md) |
| `prp-format` | review HTML 与 PRP 格式转换 | [仓库写入命令](mdf-cli-write.md) |
| `delivery` | 交付辅助（配置快照/并行；非进度关口） | [交付阶段与验证](mdf-cli-delivery.md) |
| `worktree-check` | 分派路径、角色与交接核验 | [交付阶段与验证](mdf-cli-delivery.md) |
| `bug close` | 验收后的 Bug 关闭写入 | [仓库写入命令](mdf-cli-write.md) |
| `verify` | module 级验证（smart / branch / named） | [交付阶段与验证](mdf-cli-delivery.md) |
| `codewiki-runtime` | 本地 CodeWiki 运行时准备 | [交付阶段与验证](mdf-cli-delivery.md) |
| `planning` | 规划工作区 | [仓库写入命令](mdf-cli-write.md) |
| `to` | 解析别名并确保目标 worktree | [仓库写入命令](mdf-cli-write.md) |
| `dev-pr` | 保全 develop 到 adhoc 并 reset 对齐远端 | [PR 与审查](mdf-cli-review.md) |
| `sync` | 三大 trunk 预览确认后同步 | [仓库写入命令](mdf-cli-write.md) |
| `finish-gitflow` | Gitflow 合并 | [仓库写入命令](mdf-cli-write.md) |
| `pre-gitflow-finish` | fact 前执行 hook 或检查其改动 | [仓库写入命令](mdf-cli-write.md) |
| `upgrade` | 替换已安装 Skill | [仓库写入命令](mdf-cli-write.md) |
| `integrate` | 联调 inbox 与可选 HTTP | [交付阶段与验证](mdf-cli-delivery.md) |

## 与 intent 的关系

deliver 是外层 Agent 协调 intent，复用现有 start、delivery 与 close-out 流程，不新增 deliver CLI。

- deliver 负责从尚未 start 起持续委托、并行 subagent 的 worktree 身份核验与结果交接。
- design 的 Baseline 与 converge 的 owner subagent 由各 intent 启动，CLI 不介入。
- 位置参数 target 与 `--until`（别名 `--stop-at`）、`--yolo` 由 intent 解释，不是 CLI 参数。
  其他 decision 自动裁定、confidence < 0.8 请求确认、默认走完 close-out；非 yolo 在 pr、close-out 前分别取得用户确认；细则见 deliver 契约。

CLI 不负责询问用户、判定文档语义或决定交付范围。它由 intent 在完成这些判断后调用：

| intent | 使用的 CLI |
| --- | --- |
| `init`、`bootstrap`、`migrate` | `doctor`、`init` 与 `validate` |
| `tree` | 只读 `tree` CLI，展示 draft/ready 混态依赖视图 | [交付阶段与验证](mdf-cli-delivery.md) |
| `intake`、`prp create`、`prp review` 与 `prp split` | `doctor`、`planning`、`list` 与 `make-id` |
| `prp review` | 另用 `prp-format` 生成 HTML、确认后转 ready 或回 draft |
| `bug create` | `doctor`、`list` 与 `make-id` | [交付阶段与验证](mdf-cli-delivery.md) |
| `jot` | `make-jot-id`；`jot promote` 另用 `list` 查重 | [交付阶段与验证](mdf-cli-delivery.md) |
| `archive` | `list` 与 `archive` | [仓库写入命令](mdf-cli-write.md) |
| `start` | `list` 与 `start` | [仓库写入命令](mdf-cli-write.md) |
| `adhoc` | `start --kind adhoc --name`、`verify smart` 与 `finish-gitflow` |
| `upgrade` | `upgrade` | [仓库写入命令](mdf-cli-write.md) |
| `to` | `to --target`：规划 ensure、develop 复用、deploy 检出 master、已有分支可建树 | [仓库写入命令](mdf-cli-write.md) |
| `dev-pr` | 保全 develop 到 adhoc 并 reset 对齐远端 | [PR 与审查](mdf-cli-review.md) |
| `sync` | `sync`：三大 trunk 预览确认后同步；多余分支只报告 | [仓库写入命令](mdf-cli-write.md) |
| `pr` | `pr --repo <repo> [--source <source>]`；merged 后完成，交给 close-out | [PR mode](mdf-cli-review.md) |
| `close-out` | 还会调用 `branch`、`list`、`release-closeout` 和 `finish-gitflow` | [交付阶段与验证](mdf-cli-delivery.md) |

- `next` intent 在 feature 交付分支上续办该 feature，否则优先续办在途流程，无在途时内部委托 tree。
- `$mdf next?` 直接进入 tree，不走 next。

`fact-audit`、`validate`、`semver-check` 与 `info` 提供可重复的状态、契约与版本判断。
它们是 intent 和测试的确定性基础，不是面向最终用户的直接产品入口。
