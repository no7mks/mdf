# 事实审阅旁路与报告

独立 `$mdf fact audit --against <commit>`（可加 `--quick`、`--output <path>`）走
[Fact Audit](fact-audit.md) 共用核的只读旁路；不勾 objectives、不写交付 Markdown。
交付主链另见 [交付事实审阅](fact-audit-delivery.md)。
树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve | 约束 | Git 根、参数、仓外产物位置 | 根、参数、日志目录 | 2 | 报 error 并停止，不写文件 |
| 2 | Context | 脚本 | `fact-audit --against`，保存 result | against、工作区指纹与范围 | 3 | 无 result 则停止，不写文件 |
| 3 | Facts | 约束 | 复核事实页、evidence 与结构（`--quick` 跳过） | 逐页 findings | 4 | 记 incomplete，转5 |
| 4 | Coverage | 约束 | must-cover 覆盖与 warnings（`--quick` 跳过） | 覆盖与 warnings | 5 | 记 incomplete，转5 |
| 5 | Report | 约束 | 会话形成报告并 report-check；valid 后才写 `--output` | 指纹、校验、可选文件 | valid 后写入并返回 | 输入变化回2；其余报 error，不写最终文件 |

## CLI

```bash
python3 -B "$MDF_ROOT/scripts/mdf.py" fact-audit --repo "$REPO_ROOT" --against <commit>
python3 -B "$MDF_ROOT/scripts/mdf.py" fact-audit --repo "$REPO_ROOT" --against <commit> --quick
python3 -B "$MDF_ROOT/scripts/mdf.py" fact-audit-report-check \
  --repo "$REPO_ROOT" --context-file /outside/context.json --report-file /outside/report.json
```

- against 不与 scope、base、路径混用；右端点为当前工作区（可 dirty）。
- 直接比较指定版本与当前工作区，不计算 merge-base；against 须本地可解析。
- 只读原仓库，不改 HEAD/index/refs/objects；不跑 tests/hooks/filters。
  - `--output` 只在步骤 5 校验通过后写入该路径。步骤 1–4 不创建、不覆盖它。
- 规则、manifest、modules 来自当前工作区；must-cover 见 fact-audit 审阅核。
- 步骤 3–4 只读 [双向复核标准](fact-audit.md#s3) 至 warnings；不跑普通六步的 scope 默认。
- `--quick` **只**跳过步骤 3–4 的 LLM，不换工作对象；仍保留 context 内确定性 audit / stale / uncovered。
  - 这些确定性结果仍进入报告，包括写入 `--output` 的报告。不改变它的含义。
- `--output` 不是 `fact-audit` 或 `fact-audit-report-check` 的 CLI 参数。不要放进这两条命令。
- `--quick` 退出码 2 且 stdout 含 result 时，不是步骤 2 失败。保存 result，跳过步骤 3–4，进入步骤 5。

## 报告字段

最终 report 使用 [JSON schema](../assets/templates/against-fact-audit-report.schema.json)。

| 对象 | 字段 | 含义 |
| --- | --- | --- |
| context → report | schema_version / mode / operation | 3 / against / fact-audit |
| context → report | against / worktree_sha256 | 基线 SHA；当前工作区树指纹 |
| context | input_identity | HEAD / shallow / 工具指纹 |
| report | paths / implementation_paths / document_paths | 已复核范围，不超出 context |
| report | findings / warnings / incomplete / decision | 语义与完成状态 |

- report-check 校验指纹与覆盖；输入变化则用原 against 回步骤 2，不复用旧通过结论。
- 完整覆盖三类范围、处置 warnings、无 finding/incomplete 才能 pass。
- 未传 `--output` 时，报告由会话返回，不写调用方文件，不直接 approve/merge。
- `--output <path>` 与 `--against <commit>`、`--quick` 组合。传入后先走本旁路。
  - 缺少 `--against <commit>`，或与 scope、base、路径同用时，步骤 1 报 error 并停止，不写文件。
- 会话按 schema 形成报告。用仓外 context 与仓外草稿运行 `fact-audit-report-check`。
  - 校验通过前不把草稿写入 `--output`。
  - `fact-audit` 的 context stdout 不是该文件的内容。
- `fact-audit-report-check` 返回 `ok: true` 且 `result.valid` 为 true 后，把已校验报告写入 `--output`。
  - `decision` 不是 pass 时也写入。该文件不是通过凭证。
  - 文件内容是报告 JSON，不是 context，也不是 report-check 信封。
- 校验因输入身份、工作区或 index 变化失败时，回步骤 2，不写 `--output`。
  - 这不是终止 error。其他失败报 error 并停止。
  - 不把未通过报告写成 `--output` 的最终内容。
- 本轮已写入该路径或留下半成品时，删除该文件。不删除本轮没写过的已有文件。
- 写入 `--output` 失败时报 error 并停止，并删除本轮半成品。
- 除该文件外，不改 HEAD、index、refs、objects，不写交付 Markdown，不勾 objectives。
  - 日志、context 与草稿仍在 checkout 外。`--output` 路径可在仓内外。

### 确定性校验范围

- against 与解析为 against 的 branch 先解析 diff，再执行影响集契约校验。
- evidence 仅校验已选事实页及 evidence / generated 路径覆盖 diff 的事实页。
- 链接校验 diff 来源页的出链，以及其他页指向 diff 路径的入链；Markdown/HTML
  目标的 anchor 缺失也报 `link.broken`。
- 对象与发布记录校验变更来源及受影响的引用约束；读取 inventory 不代表全库校验。
- 范围外事实页不注册 evidence 进度组，也不进入本轮失败结果。
- 显式 full 入口按全库范围运行 closeout 静态规则。
