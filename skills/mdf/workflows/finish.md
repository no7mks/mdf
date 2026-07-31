# Finish

只在用户显式调用 `$mdf finish` 时运行。不要因代码完成、测试通过、分支合并或
定时任务隐式触发；不要自动 commit。

完整读取 `workflows/common.md`、`workflows/audit.md`、
`references/repository-contract.md`、`references/object-contract.md` 与
`references/workflows.md`。

1. 在 clean worktree 运行 `doctor` 与 `branch`。manifest 非 ready、detached
   HEAD 或非 Gitflow 分支均停止。分支只可为 `feature/*`、`bugfix/*`、
   `release/<semver>`、`hotfix/<semver>`。
2. 在任何写入前内部执行 audit：release 用 release audit，其他支持分支用
   change audit。
3. feature/bugfix：无未解决 finding 时，使用 `planning-candidates`、
   `move-change` 或最小 Change 目录准备变更；写入事实修复与
   `changes/unreleased/<slug>/CHANGE.md`，复读内容并运行 targeted validation。
   对象保持 ready，不创建版本目录或 closeout 根文件。
4. release/hotfix：有 finding 时可写事实修复但必须停止；用户 commit 后再次
   `$mdf finish`。零 finding 时组装非空 summary 的 semantic attestation；
   release 读取全部 unreleased child Change，hotfix 传入严格的实际结果 JSON，
   再调用 `release-closeout`。用户要求预览时才加 `--dry-run`。
5. Bug outcome：`fixed` 写 `fixed_in`；`closed` 只允许非 fixed 终态；
   `deferred` 保持 ready。critical 只能 fixed；major deferred/wont-fix 必须有
   用户接受、理由和 follow-up；duplicate 不进入 outcome。

## Gitflow 合并续办

若本次写入了事实或 Change，展示结果、验证通过后停止；用户复核并 commit，再次
显式调用 `$mdf finish`。续办从 clean worktree 开始，调用：

```bash
python3 "$MDF_ROOT/scripts/mdf.py" finish-gitflow --repo "$REPO_ROOT"
```

CLI 先 fetch，并要求当前源分支及所有参与的 master/develop 分支与 upstream 完全
一致。feature/bugfix 以 no-ff 合并到 develop；release/hotfix 以 no-ff 合并到
master，再以 no-ff 将 master 合并到 develop。release/hotfix 创建带注释的
`v<semver>` tag。随后以原子 push 推送目标分支和 tag、删除远端源分支，并删除本地
源分支。

冲突时 CLI 立即 abort 并恢复 merge 前状态，不推送、不删分支。询问用户如何继续，
并建议由 MDF 分析和解决；涉及写入时仍须复核、commit 后再次调用 finish。
