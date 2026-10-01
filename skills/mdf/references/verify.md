# verify

对当前交付分支运行 module 级验证。开发中只用 on-site；closeout 前才跑 full。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Resolve modules                │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ module 已确定
┌──────────────────────────────────┐
│ 2 Select                         │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 范围与命令已定
┌──────────────────────────────────┐
│ 3 Run                            │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败 ────→ [停止并报告]
                 │
                 ▼ 命令通过
┌──────────────────────────────────┐
│ 4 Record                         │
└────────────────┬─────────────────┘
                 │
                 ├──── full 失败 ────→ [停止并报告]
                 │
                 ▼ on-site 结束或 full 已记录
                 [结束]
```

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve modules | 脚本 | 读 modules；定 on-site 范围；full 要干净树 | module 列表 | 2 | 停止并报告 |
| 2 | Select | 约束 | on-site 选题；full 按分支选 smoke/release | 命令列表 | 3 | 停止并报告 |
| 3 | Run | 脚本 | 跑 lint/build/quick；full 跑并集；on-site 加 `--test` | 运行结果 | 4 | 停止并报告 |
| 4 | Record | 脚本 | full 写 `verify.full.json`；可 `advance` | 证据或摘要 | 结束 | 停止并报告 |

### 1 Resolve modules

- 读 `.mdf/modules.yaml`。
- on-site：`--paths` 命中 sourceset（非 ignore）并与 `--module` 合并。
- full：全部 module；执行前 worktree 必须干净。

验收：涉及 module 非空且均已声明。

异常与交接：未知 module 或 full 时 worktree 脏则停止。

### 2 Select

**on-site**

1. 收集涉及 module 的 named suite 列表。
2. 打开 `docs/system/testing/<suite>.md`，摘要目的与 testcase 构成。
3. 组装改动摘要。
4. Jev（或主 Agent）决定跑哪些 test/testcase；经 `--test` 传入。
5. ❌ 默认不整份跑 named suite。

**full**

- `release`/`hotfix` → release 并集；其他工作分支 → smoke 并集。

验收：命令列表不超出涉及 module。

异常与交接：选题失败则停止。

### 3 Run

- CLI：`mdf.py verify run --level on-site|full ...`
- 失败则停止并报告。

验收：所选命令通过。

异常与交接：`verify_command_failed` 时停止。

### 4 Record

- full 成功写入 `changes/unreleased/<slug>/verify.full.json`，`commit`=HEAD。
- `check`：证据有效且相对 HEAD 仅允许证据/报告增量。
- HEAD 有业务 diff：先 Jev 判是否重跑；否 → `advance`；是 → 再 `run`。
- on-site 不持久化门禁。

验收：full 证据可 `check`；on-site 结果在 stdout。

异常与交接：证据缺失或过期则停止。
