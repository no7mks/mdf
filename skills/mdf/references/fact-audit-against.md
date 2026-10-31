# 事实审阅旁路与报告

独立 `$mdf fact audit --against <commit>`（可加 `--quick`）走
[Fact Audit](fact-audit.md) 共用核的只读旁路；不勾 objectives、不写交付 Markdown。
交付主链另见 [交付事实审阅](fact-audit-delivery.md)。
树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve | 约束 | Git 根、参数、仓外产物位置 | 根、参数、日志目录 | 2 | 报 error 并停止 |
| 2 | Context | 脚本 | `fact-audit --against`，保存 result | against、工作区指纹与范围 | 3 | 读日志，报 error 并停止 |
| 3 | Facts | 约束 | 复核事实页、evidence 与结构（`--quick` 跳过） | 逐页 findings | 4 | 记 incomplete，转5 |
| 4 | Coverage | 约束 | must-cover 覆盖与 warnings（`--quick` 跳过） | 覆盖与 warnings | 5 | 记 incomplete，转5 |
| 5 | Report | 约束 | 仓外 JSON + report-check | 指纹、校验结果 | 有效则返回 | 变化回2；其余报 error |

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
- 规则、manifest、modules 来自当前工作区；must-cover 见 fact-audit 审阅核。
- 步骤 3–4 只读 [双向复核标准](fact-audit.md#s3) 至 warnings；不跑普通七步的 scope 默认。
- `--quick` **只**跳过步骤 3–4 的 LLM，不换工作对象；仍保留 context 内确定性 audit / stale / uncovered。

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
- 报告由会话返回；调用方保存到 checkout 外；不直接 approve/merge。

### 确定性校验范围

- against 与解析为 against 的 branch 先解析 diff，再执行影响集契约校验。
- evidence 仅校验已选事实页及 evidence / generated 路径覆盖 diff 的事实页。
- 链接校验 diff 来源页的出链，以及其他页指向 diff 路径的入链；Markdown/HTML
  目标的 anchor 缺失也报 `link.broken`。
- 对象与发布记录校验变更来源及受影响的引用约束；读取 inventory 不代表全库校验。
- 范围外事实页不注册 evidence 进度组，也不进入本轮失败结果。
- 显式 full 入口保留全库 doctor；不通过 base/after finding 差集裁定影响集。
