# Contract switch

使用本次已经固定的 `MDF_ROOT` 切换契约。

```bash
python3 -B "$MDF_ROOT/scripts/mdf.py" contract-switch --repo "$REPO_ROOT"
```

该命令把业务仓的 `schema_version` 改到本机 `SCHEMA_VERSION`。

## 条件

- 目标是 Git 根，工作区 clean。
- 当前分支等于 workflow trunk。
- manifest 恰好有一行 `schema_version: <整数>`。
- 进程持有 finish lock。

不检查 check entry、在途分支或其他门禁。

## 结果

| 声明值 | 结果 |
| --- | --- |
| 等于本机契约 | `changed: false`，不提交 |
| 小于本机契约 | 只改这一行并提交 |
| 大于本机契约 | 错误 `contract_tool_outdated`，提示 `$mdf upgrade` |

- 提交说明是 `chore(mdf): 切换 MDF 契约到 N`。
- PR mode 使用分支 `codex/contract-switch`。
- 其他模式直接提交到 trunk。不 push。

## 快速放行

CI 对 `codex/contract-switch` 只接受同时满足这些条件的提交：

- 只有一个 parent，且该 parent 是目标 tip。
- 目标分支是 workflow trunk，仓库处于 PR mode。
- diff 只有 `.mdf/manifest.yaml`。
- 旧值是小于本机契约的整数，新值等于本机契约。
- 该行以外的内容不变。
