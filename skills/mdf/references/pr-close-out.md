# PR Close-out

## 决策树

```text
┌──────────────────────────────┐
│ 1 Check                      │
└──────────────┬───────────────┘
               ├──── 不符 ────→ [保留现场，停止]
               ▼ 通过
┌──────────────────────────────┐
│ 2 Prepare                    │
└──────────────┬───────────────┘
               ├──── 缺前置 ────→ [交接主链]
               ▼ 已准备或恢复
┌──────────────────────────────┐
│ 3 Finish                     │
└──────────────┬───────────────┘
               ├──── 失败 ────→ [读日志，保留现场]
               ▼ 返回实际状态
┌──────────────────────────────┐
│ 4 Report                     │
└──────────────┬───────────────┘
               ├──── 等待 ────→ [交接，用户合并后续办]
               └──── 完成 ────→ [核验清理结果，返回调用方]
```

## 工作流（唯一执行契约）

本表只由 PR mode 的 close-out 或其恢复调用。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check | 约束 | 核模式、source、origin 与目标现场 | 配置与 Git 状态 | 2 | 保留现场，停止 |
| 2 | Prepare | 约束 | 首次完成主链前置；恢复核对操作记录 | 材料或恢复记录 | 3 | 交接主链 |
| 3 | Finish | 脚本 | 调用 finish-gitflow 提交或续办 | CLI 状态与平台事实 | 4 | 读日志，保留现场 |
| 4 | Report | 约束 | 只在 completed=true 时报告完成 | 远端引用与清理结果 | 返回调用方 | 等待交接；状态不符停止 |

## 模式与入口

本页规定 `closeout.mode: pr` 时的交付与恢复。

```yaml
closeout:
  mode: pr
  provider: github # 或 gitlab
```

- 省略 closeout 时使用 local；init 保留配置，doctor 校验。
- origin fetch/push 地址须一致且唯一，支持 SSH/HTTPS 与自建 host；第一版只支持同仓 PR/MR。
- 项目安装并登录 gh/glab；MDF 不自动配置账号、CI、runner 或 branch protection。
- 初次 close-out 仍按主链完成集成、审查、验证、fact 和材料准备；随后委托本页提交。
- PR mode 的 feature PRP 在源提交中准备 implemented，随 PR 合入 develop 后生效。
- 源分支的候选状态不代表已交付；交付完成看远端目标分支和实际合并结果。
- 已有 Git common dir `mdf/finish/<source>.json` 时先续办本页，不重新执行整套材料准备。

## 生命周期

本节按平台实际状态推进 finish，不按退出码或 checklist 猜测完成。

| 状态 | 操作 |
| --- | --- |
| 尚无 PR/MR | `finish-gitflow --repo <owner>` 提交候选状态、push 源提交、创建或查回复用 |
| open | 返回 waiting_for_merge；保留分支与 worktree，用户合并后再执行 finish |
| 源分支前进 | feature/bugfix/adhoc 先完成受影响的主链检查，再复用 PR/MR；不改写历史 |
| closed，未 merged | 返回 closed_without_merge；不清理、不宣称完成 |
| merged | 核 source/target/head、双亲 merge commit、远端第一父链，然后续办 |
| 仅部分后续动作成功 | 核对记录与实际状态，只补剩余步骤 |
| completed | 本地 source 删除、owner detached；保留工作区，按原清理规则交接 |

- 从主工作区恢复：`finish-gitflow --repo <主路径> --source <原分支>`，支持所有交付 kind。
- 返回 completed=false 是正常等待；调用方须读取 status，不得因退出 0 就结束 deliver Goal。
- PR/MR 由用户或项目 CI 合并；finish 不批准或合并平台 PR/MR。
- 已收口 release/hotfix 的源提交前进时报告 publish_state_changed，保留版本目录。
- 首次 push 或创建结果丢失，重入先查平台，禁止重复创建或覆盖记录。
- tag、远端、来源或目标不符时停止；不 reset、不覆盖 tag、不清理他人现场。

## 发布与回合

本节固定本次发布的实际 merge commit M。

1. 确认 release/hotfix 已通过平台 merge commit 合入 master。
2. 在 M 创建 annotated `v<version>`，正文沿用 CHANGELOG 条目，只 push tag。
3. 在独立临时 worktree 将 M no-ff 合回 develop，并验证远端包含 M。
4. 全部完成后清理本地交付 source；临时回合目录保留供检查，不删除主目录。

- 不跟随后来前进的 master HEAD；本地 master/develop 只做同名 ff 同步，分歧时保留现场。
- tag 已发布、回合未完成时返回 published_pending_backmerge。
- 冲突保留在返回的 backmerge.worktree；解决、提交后再次 finish，转为回合 PR/MR。
- 平台拒绝直接 push develop 时创建回合 PR/MR；用户合并后再次 finish。
- 等待期间 develop 前进，可在回合 worktree 合入、解冲突并追加提交；finish 非 force push 后复用原 PR/MR。
- 新 head 必须保留记录的历史和固定 M；改写历史仍停止。回合 PR 可使用同一 CI reviewer。
- tag push 响应丢失时先核对远端；已存在且符合记录则复用。
- local 模式继续原子 push master + tag，develop 只在本地回合。

## Merge 例外

本节约束 MDF 的 Git 入口；平台可保留正常 push 权限。

| 操作 | PR mode |
| --- | --- |
| feature/bugfix/adhoc → develop；release/hotfix → master | PR/MR |
| planning → develop | 完整文档白名单才允许 no-ff |
| master → develop | 允许固定 master 历史提交 no-ff 回合 |
| develop 上纯 MDF/宿主维护 | 允许直接提交和 push |
| 其他合入 master/develop | 拒绝，提示 PR/MR |
| trunk → owner、角色分支 → owner | 沿用现有集成 |

- 完整文档白名单：docs/、changes/、根 *.md、.mdf/ 及以下全部宿主目录。
- 宿主目录：.agents/、.claude/、.codex/、.cursor/、.kiro/、.openclaw/，不限定 skills/mdf。
- develop 直接维护仅允许 .mdf/、宿主目录、根 AGENTS.md；不判断是否由 upgrade 产生。
- 混入其他路径须 PR/MR；master 不增加文件维护例外；禁止 rebase 或跨分支 ff-only。
- planning 检查独有普通提交、rename/delete 原路径、merge resolution 及最终增量，防止 revert 掩盖代码修改。
- sync 拒绝分叉的 master/develop，以及无法证明合规的本地领先增量；同名 ff 同步允许。
- push 后审计与项目配置见 [CI 接入](ci-review.md)。
