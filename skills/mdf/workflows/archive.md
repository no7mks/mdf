# Archive

只在用户显式调用 `$mdf archive` 时执行。不要因对象 closed、目录变大或发布完成
而自行触发；不要自动 commit。

完整读取 `workflows/common.md`、`references/repository-contract.md`、
`references/object-contract.md` 与 `references/workflows.md`。

1. 用户提供精确 `MAJOR.MINOR` 切片 `RELEASE_EPOCH`；拒绝 patch、预发布、
   构建元数据和 `unreleased`。解析 `REPO_ROOT` 并运行 `doctor`，只有 ready 与
   clean 时继续。
2. 用户要求预览时才运行 `archive --epoch "$RELEASE_EPOCH" --dry-run`；预览
   只检查 closed Requirement/Bug 的稳定移动和仓库内 canonical 引用重写，
   不构成确认或参数绑定。
3. closed duplicate 永远随 canonical 组成 archive group。canonical 仍为 ready
   时 CLI 返回 `duplicate_group_open`，不得单独移动 duplicate。
4. 用户显式调用本命令即授权实际归档：运行 `archive --epoch "$RELEASE_EPOCH"`。
   CLI 写入后做 full validation；失败保留现场，成功报告对象、切片、重写数量和
   validation 结果。
