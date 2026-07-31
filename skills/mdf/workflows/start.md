# Start

只在用户显式调用 `$mdf start` 时执行。完整读取 `workflows/common.md` 与
`references/workflows.md`。一次只启动一个分支，不自动 commit。

1. 询问分支类型和必要标识：feature/bugfix 需要 slug；release/hotfix 需要稳定
   SemVer。不得从自然语言猜测版本。
2. 调用：

   ```bash
   python3 "$MDF_ROOT/scripts/mdf.py" start --repo "$REPO_ROOT" \
     --kind '<feature|bugfix|release|hotfix>' [--name '<slug>'] \
     [--version '<semver>']
   ```

3. CLI 必须先 fetch，要求 `origin` 存在、仓库默认分支为 `master`、来源分支及其
   upstream 完全一致，且 worktree clean。feature、bugfix、release 从 develop
   创建；hotfix 从 master 创建。目标分支在本地和远端均不得存在。
4. 成功时 CLI 创建分支、推送到 origin 并设置 upstream。失败时不创建分支，报告
   finding；若基线已推进，先询问用户并建议由 MDF 分析和解决。
