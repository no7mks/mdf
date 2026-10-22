# MDF CLI：PR mode 与 CI reviewer

本页记录确定性 CLI 的输入与副作用；语义规则见 Skill 的 PR Close-out 和 CI 接入。

## 配置与 close-out

本节说明可选模式与 close-out 返回状态。

- manifest.closeout.mode 为 local/pr，省略为 local；pr 需 provider: github/gitlab。
- init 保留已有 closeout，doctor 报 manifest.closeout finding；schema_version 仍为 3。
- `finish-gitflow --repo <repo> [--source <source>]` 在 pr 模式支持所有交付 kind 的恢复。
- 返回 mode、completed、status、pull_request、merge_commit、backmerge、tag、deleted 与工作区路径。
- waiting_for_merge、closed_without_merge、published_pending_backmerge 都是 completed=false。
- completed=true 后才能报告交付完成；正常等待退出 0，不重复创建远端对象。
- PR mode 可能提交候选 PRP 状态、push 源分支、创建 PR/MR、tag 与回合 develop。
- local 模式的原本地收口和发版语义保留。

## 检查命令

本节列出只读业务检查；CLI 的运行日志仍按统一约定落盘。

| 命令 | 参数 | 输出与失败语义 |
| --- | --- | --- |
| audit-push | --repo --branch --before --after；可选 --evidence-file 或 --collect-evidence | result.verdict 为 pass/violation/needs-review，退出 0 不代表合规 |
| review-context | --repo --source --head --policy-ref；可选 --review-base --previous-report | result 为固定上下文，缺身份或基线失败，材料缺项写 incomplete |
| review-report-check | --context-file --report-file | 通过返回 result.valid 和规范化 report；坏格式或不完整契约非零 |

- audit-push 仅审 develop/master；默认离线，显式 collect-evidence 才 fetch 并查询平台。
- evidence 文件由可信 CI controller 提供，sources 需能验证为 origin 历史，PR 证明匹配实际双亲。
- review-context 和 CI review.py 的成对 --source-commit/--target-commit 选择独立只读模式，--source 可省略。
  - mode=commits，不依赖 roster 或交付材料；每次使用唯一 merge-base→source，提供 target_diff/target_paths。
  - 不混用 head/policy-ref，不接受 review-base/previous-report；缺失或多个 merge-base 失败。
  - 使用 commit-review-report.schema.json，直接校验 findings、覆盖与结论；无 delivery 或 reviewers 字段。
- 以下 delivery、回合与 release 规则仅用于未传 commit 参数的交付模式。
- review-context 支持 detached checkout，从已提交 delivery.json 冻结 roster 与基线。
- 回合 source 从发布 tag 和 no-ff 双亲恢复上下文，kind 为 backmerge；publication 包含固定发布提交与原 source。
- release 首轮使用 policy_ref 的上一正式发布 tag，首次无版本需显式 --review-base。
- report-check 支持 Cursor JSON result envelope；不会修补不符合 schema 的模型文本。
- report-check 不是语义裁定，也不是交付 gate；不写 objectives 或 code-review.md。

## 接入与运行证据

本节路由到安装后的接入入口。

- [PR Close-out](../../../skills/mdf/references/pr-close-out.md)：提交、发布、恢复与白名单。
- [共用 Review 协议](../../../skills/mdf/references/reviewer-protocol.md)：只读 reviewers 和 owner 裁定。
- [CI 接入](../../../skills/mdf/references/ci-review.md)：Codex/Cursor、workflow、报告和平台发布示例。
