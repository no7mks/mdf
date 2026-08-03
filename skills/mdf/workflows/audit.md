# Audit

只在用户显式调用 `$mdf audit`，或被同一次 `$mdf finish` 内部委托时执行。
审计只读：不写入、移动、提交或生成持久报告。

完整读取 `workflows/common.md`、`references/repository-contract.md`、
`references/object-contract.md` 与 `references/workflows.md`。

1. 解析 `REPO_ROOT` 并运行 `doctor`。`clean` 必须为 `true`、manifest 必须为
   `ready`；否则停止，未初始化时仅建议 `$mdf init`。
2. 运行 `branch --repo`：`release/<semver>` 执行 release audit；
   `feature/*`、`bugfix/*`、`hotfix/<semver>` 执行 change audit；其他分支停止。
   记录 HEAD、分支与 status，审计期间任一变化则废弃结果。
3. change audit：feature/bugfix 使用 `develop...HEAD`，hotfix 使用
   `master...HEAD`；检查变更涉及的代码、配置、schema、测试和文档，反向核对
   受影响事实与 evidence，并运行 targeted validation。
4. release audit：要求本地 `develop`，全量审阅当前事实页、ADR 和本次 Change
   引用对象，并运行 full validation。所有 unresolved finding 阻断 closeout，
   不提供 waiver。
5. 返回会话内结构化摘要：审计类型、基线、HEAD、覆盖内容、未触及理由、
   findings 与 `semantic`/`finding_count`。只有零 finding、passed 的摘要可供
   `$mdf finish` 组装 closeout attestation。
