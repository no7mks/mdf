# MDF CLI：PR mode 与 CI reviewer

本页记录确定性 CLI 的输入与副作用；语义规则见 Skill 的 PR、合并后续办和 CI 接入。

## 配置与 close-out

本节说明可选模式与 close-out 返回状态。

- manifest.closeout.mode 为 local/pr，省略为 local；pr 需 provider: github/gitlab。
- init 保留已有 closeout，doctor 报 manifest.closeout finding；schema_version 仍为 3。
- `pr --repo <repo> [--source <source>] [--pull <id>]` 创建/更新 PR，返回 waiting_for_merge 或 closed_without_merge。
- `pr-watch --repo <repo> [--source <source>] [--pull <id>] [--head <sha>]` 查询平台 PR/MR、review 与关联 CI，合并核验时 fetch 目标远端 ref。
  - 返回 `merged`、`closed_without_merge`、`changes_requested`、`ci_failed` 或 `merge_conflict`，附平台快照。
  - `--head` 固定已确认的源 SHA。省略时取初始平台 head，轮询期间变化返回 `pull_state_changed`。
  - 每次轮询快照写入该次 CLI 日志目录的 `polls.jsonl`。
  - `--origin-run <id>` 补充已确认的发起 PR/MR 或执行 merge 的 run/pipeline ID，可重复传入。允许 skipped 或 neutral 时使用 `--allow-skipped`。
  - `--handled-review <id>` 可重复传入已完成返工的 `change_requests` ID。平台 review 状态仍保留在快照。
  - `merged` 表示通过 Git 合并核验和关联 CI 即时复查。随后用 `pr` 确认交付现场并交接 close-out。
  核验实际 merged 后返回 completed=true、status=merged、next_intent=close-out，不发布或清理。
- `finish-gitflow --repo <repo> [--source <source>] [--pull <id>]` 在 pr 模式支持所有交付 kind 的恢复。
- 返回 mode、completed、status、pull_request、merge_commit、backmerge、tag、deleted、remote_deleted 与工作区路径。
- finish-gitflow 仅续办 merged 后的操作；未 merged 返回 pr_not_merged，不创建/更新 PR。
- waiting_for_merge、closed_without_merge、published_pending_backmerge 都是各自 operation 的 completed=false。
- gitflow 发布后以固定 merge commit no-ff 回合并直接 push develop；不创建回合 PR/MR。
- github-flow release 的 tag 由前置 publish 创建并推送，指向固定 `release_head`；close-out 核验 tag 与主线合入结果。
  冲突或 push 未完成时保留 backmerge worktree；push 失败详情见 backmerge.push_error。
- finish-gitflow 的 completed=true 后才能报告交付完成；正常等待退出 0，不重复创建远端对象。
- source 清理再次检查 worktree 占用，并以已确认 head 原子删除 ref；并发前进时拒绝删除，保留分支配置。
- PR mode 先以显式 expected SHA lease 删除 origin 的原 source，确认缺失后才清理本地 source；remote_deleted 为独立 bool。
  远端失败时保留本地 branch/worktree；不删除 trunk 或 tag。
- 清理重试直接查询远端 ref。已缺失即继续；已变更的 SHA 保留现场。
- 发布重试核对实际 tag 及 develop 的回合拓扑。
- 多个同源 PR/MR 需要显式传 `--pull <id>`。平台的 source、target 和 head 必须与操作相符。
- 涉及共享工作区或 ref 的写入持有 Git common dir 的 OS lock。并发返回 `finish_busy`，进程退出自动释放。
- PR mode 的 release/hotfix 候选材料已进入版本目录时，delivery 与 verify branch 在该目录读写，不复制回 unreleased。
- PR mode 可能提交候选 PRP 状态、push 源分支、创建 PR/MR、tag 与回合 develop。
- local 模式的原本地收口和发版语义保留。

## 检查命令

本节列出只读业务检查；CLI 的运行日志仍按统一约定落盘。

| 命令 | 参数 | 输出与失败语义 |
| --- | --- | --- |
| audit-push | --repo --branch --before --after；可选 --evidence-file 或 --collect-evidence | result.verdict 为 pass/violation/needs-review，退出 0 不代表合规 |
| review-context | --repo --source --head --policy-ref；可选 --review-base --previous-report | result 为固定上下文，缺身份或基线失败，材料缺项写 incomplete |
| review-report-check | --context-file --report-file | 通过返回 result.valid 和规范化 report；坏格式或不完整契约非零 |
| review-prepare | --repo；可选 --against --initial-base --force | 左端点、净增量、体积、project rule 和 `skip_review` |
| review-record | --repo --against --head；可选 --initial-base --failed | 完整审查通过后记录当前 clean HEAD；--failed 使同内容旧记录失效 |

- audit-push 从 `before` 读取 workflow。gitflow 接受 trunk 与 develop；github-flow 接受 trunk 与 `support/*`。
  - `support/*` 合入 trunk 为 `support_merge_forbidden`。默认离线，显式 collect-evidence 才访问平台。
  - 切换 PR/MR 的审计见 [Workflow 切换](../../../skills/mdf/references/workflow/switch.md#首次-push-审计)。
- evidence 文件由可信 CI controller 提供，sources 需能验证为 origin 历史，PR 证明匹配实际双亲。
- review-context 的 --against <commit> 选择独立只读模式，不接受 source/head/policy-ref。
  - mode=against，要求 worktree clean；直接比较指定历史版本与当前 HEAD，不计算 merge-base。
  - 不接受 review-base/previous-report；不生成 target_diff/target_paths。
  - 强制 paths 仅含 sourceset ∩ ¬module-ignore 的实现变更；文档与交付材料不进覆盖清单。
  - 使用 against-review-report.schema.json，绑定 against、head、规则与 context 指纹。
- 以下 delivery、回合与 release 规则仅用于未传 against 的交付模式。
- review-context 支持 detached checkout，从已提交 delivery.json 冻结 roster 与基线。
- 回合 source 从发布 tag 和 no-ff 双亲恢复上下文，kind 为 backmerge；publication 包含固定发布提交与原 source。
- release 首轮使用 policy_ref 的上一正式发布 tag，首次无版本需显式 --review-base。
- report-check 支持 Cursor JSON result envelope；不会修补不符合 schema 的模型文本。
- report-check 不是语义裁定，也不是交付 gate；不写 objectives 或 code-review.md。
- review-prepare 有 clear commit 时比较两端，无需 ancestor。正常左端点为交付 start_commit；
  release 用上一正式发布；非交付分支传 `--against`，首次 release 可传 `--initial-base`。
- `net_increment` 是实际审查范围；`--force` 使用正常左端点。dirty 仍读取 clear commit，
  输出暂存、未暂存和未跟踪改动的审查范围，此时 `skip_review` 为 false。
- `size.reviewers` 按 numstat 新增与删除之和向上取整，每 1000 行一人；跳过时人数为 0。
- review-record 检查实际审查范围是否覆盖全部增量。独立指定的局部范围不能推进 clear commit。

## 接入与运行证据

本节路由到安装后的接入入口。

- [PR](../../../skills/mdf/references/pr.md)：提交、等待与修复。
- [合并后续办](../../../skills/mdf/references/pr-close-out.md)：发布、恢复与白名单。
- [共用 Review 协议](../../../skills/mdf/references/reviewer-protocol.md)：只读 reviewers 和 owner 裁定。
- [CI 接入](../../../skills/mdf/references/ci-review.md)：Codex/Cursor、workflow、报告和平台发布示例。

## Develop 与 Trunk 接管

`mdf.py trunk-pr --repo <root> [--slug <slug>]` 仅用于 github-flow + PR mode，接管后将本地 trunk 对齐 `origin/<trunk>`。
返回 `kind`、`source` 与 `worktree`。对齐后重试返回 `no_pending_commits`。见 [trunk-pr 契约](../../../skills/mdf/references/trunk-pr.md)。


`mdf.py dev-pr --repo <root> [--slug <slug>]` 仅准备本地现场：fetch、保全 develop HEAD
到 adhoc worktree、reset develop 到固定 origin/develop。返回 source、worktree 与 next_intent。
sync 的 `dev_pr_required` 委托同一 intent。续办使用返回的 `source` 与实际平台状态。
项目 trivial 路径覆盖见 [dev-pr 契约](../../../skills/mdf/references/dev-pr.md)。

## 审查范围

code-review against 要求 clean；fact audit against / `--scope branch` 比较基线与当前工作区（可 dirty），
`--quick` 只跳过 LLM。强制覆盖实现变更（sourceset ∩ ¬ignore）。

- code-review：实现变更与 sourceset 求交后再排除 module ignore；未归属实现不进入 paths、diff 或覆盖检查。
- 重叠归属须所有 owner 均忽略才排除；删除和 rename 的新旧路径分别判定。
- code-review 不把项目文档和交付材料列入强制 paths；reviewer 可读但不纳入覆盖校验。
- against code-review：worktree 必须 clean；规则、AGENTS、manifest、modules 从当前 HEAD 读取；context 绑定 against 与 head SHA。
- fact audit against / branch：比较 against → 当前工作区；`worktree_sha256` 为工作区树指纹；仓外 snapshot 不改原仓库。

### Release 集成审查

- `codex/integrate/release-<version>` 的 review-context 复用对应 release 材料，返回 `kind: integration`。
- `delivery_base` 固定为已发布 final tag 的 commit，审查覆盖发布后主线集成的增量。
- 集成 worktree 支持 catch-up-plan、delivery route、smart verify 与 catch-up 自勾，记录提交在集成分支。
