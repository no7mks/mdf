# Finish

不要自动 commit。

完整读取 `intents/common.md`、`intents/audit.md`、
`references/repository-contract.md` 与 `references/object-contract.md`。

## 交付前检查

1. 运行 `doctor` 与 `branch`。`manifest` 非 `ready`、detached HEAD 或非 Gitflow
   分支均停止。分支只可为 `feature/*`、`bugfix/*`、`release/<semver>`、
   `hotfix/<semver>`。
2. 在任何写入前，按分支计算交付范围：feature/bugfix 使用 `develop...HEAD`，
   hotfix 使用 `master...HEAD`；release 要求本地 `develop`。检查该范围涉及的代码、
   配置、schema、测试、`当前事实文档`、Proposal、Bug 与 Change，并识别需要更新
   的`当前事实文档`。这是`交付前检查`，不是 `audit`。
3. feature/bugfix：需要迁入仓库内既有材料时，要求用户明确给出来源目录；展示来源、
   `changes/unreleased/<slug>` 目标及链接重写，并取得确认后才以 `move-change`
   迁入。来源目录名的 slug 必须等于分支 slug，且不得含符号链接；目标冲突、来源含有
   目标或非 canonical `CHANGE.md` 时停止。没有既有材料时创建最小 Change 目录。完成
   必要的`当前事实文档`修复与
   `changes/unreleased/<slug>/CHANGE.md`。对象保持 `ready`，不创建版本目录或
   closeout 根文件。
4. 内部委托 `audit`：release 执行`全量审阅`；其他分支对本次实现变更与受影响文档
   执行`范围审阅`。范围审阅必须传入本节计算的精确实现和文档路径。若 audit 有
   finding，或用户未当场确认其 warning 与语义摘要，可修复文档但必须停止；用户复核、
   commit 后再次调用 `$mdf finish`。
5. release/hotfix 在 audit 零 finding 后执行版本收口。release 读取并移动全部
   unreleased child Change；hotfix 必须无 unreleased Change，并提供实际结果 JSON。两者
   都提供规范 `--release-date`。Core 只记录已验证的确定性审计；语义审阅由本次
   `finish` 中已确认的 audit 负责。用户要求预览时才加 `--dry-run`。
6. hotfix 的 `--hotfix-change-json` 只允许 body、outcome、ADR、
   `closed_resolutions`、`release_notes`、`breaking` 与 `evidence`；body 非空，三类
   evidence 为字符串列表且合计至少一条，release notes 至少有一条非空类别。Core 注入
   `change_kind` 与 `source_branch`；未知字段、空字符串或缺失必填字段均停止。
7. 调用 `release-closeout` 时，`--closures-json` 覆盖每个 child Change 声明的
   outcome，并可补录未写入 child Change 的 Proposal/Bug。每个 `ready` 且
   `found_in: unreleased` 的 Bug 必须分类：`fixed` 关闭并写 `fixed_in`；`closed`
   只写非 fixed 终态；`deferred` 保持 `ready`。critical 只能 `fixed`；major
   deferred/wont-fix 必须有用户接受、理由和 follow-up；duplicate 不进入 outcome。
   canonical 与 duplicate 作为一个 archive group 一并归档。
8. 版本根 Change 聚合 child Change 的 outcomes 与 `evidence`；每类 evidence 按首次
   出现顺序去重，并追加 `manifest.verification.commands`。preview 不执行命令；apply
   在目标仓库执行命令后必须保持 clean worktree，随后写入。失败现场保留给用户检查。

## Gitflow 合并续办

若本次写入了`当前事实文档`或 Change，展示结果、验证通过后停止；用户复核并 commit，再次
显式调用 `$mdf finish`。续办时调用：

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
