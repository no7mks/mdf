# Archive

完整读取 `intents/common.md`、`references/repository-contract.md` 与
`references/object-contract.md`。

## 决策树

```text
精确 MAJOR.MINOR → doctor ready 且 clean？否：停止；是 → 可选预览
→ duplicate group 可归档？否：停止；是 → archive → full validation
```

## 工作流（唯一执行契约）

1. **约束**；要求精确 `MAJOR.MINOR` 的 `RELEASE_EPOCH`，拒绝 patch、预发布、
   构建元数据和 `unreleased`；证据：有效 epoch；通过 → 2；失败 → 停止。
2. **脚本**；解析 `REPO_ROOT`、运行 `doctor` 并检查 clean；证据：`ready` 与 clean；
   通过 → 3；失败 → 停止。
3. **脚本**；仅在用户要求预览时运行 `archive --epoch "$RELEASE_EPOCH" --dry-run`；
   证据：稳定移动与 canonical 引用重写预览；通过 → 4；失败 → 停止。预览不构成确认或
   参数绑定。
4. **约束**；closed Proposal、closed/rejected Bug 的 duplicate 必须随 canonical 组成
   archive group；证据：archive group 关系；通过 → 5；失败 → 停止，不得单独移动。
5. **脚本**；本调用授权运行 `archive --epoch "$RELEASE_EPOCH"`，后运行
   `full validation`；证据：对象、切片、重写数量与 validation；通过 → 结束；失败 →
   `duplicate_group_open` 时停止且不得单独移动，其他失败保留现场并报告 findings。绝不自动 commit。
