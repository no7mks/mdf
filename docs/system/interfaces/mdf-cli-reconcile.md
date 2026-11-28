# Reconcile CLI

`mdf.py reconcile` 接入混合流程的发布记录。
执行顺序、JSON 输入与 evidence 契约统一见 [Reconcile](../../../skills/mdf/references/reconcile.md)。

## 子命令

| 命令 | 输入 | 结果 |
| --- | --- | --- |
| inspect | repo；可选 version/tag/commit/support | 只读返回 ledgerless 候选或 post_hoc 版本队列 |
| prepare | 与 inspect 相同 | 建立或复用受控工作区与本地操作记录 |
| apply | repo、version、release-date、record-file | 预检全部材料后写入并提交；不自动推进对象状态 |
| finish | repo；可选 record-only/yolo/evidence-file/source | 记录止步、等待接管确认或推进原发布链 |

所有参数使用 `--` 前缀。`--source` 用于清理中断后的续办或完成状态查询。
操作记录位于 Git common dir 的 `mdf/reconcile/`，不替代交付账本或外部 evidence。

## 实现边界

| 模块 | 职责 |
| --- | --- |
| reconciliation/context | 发布线、候选、版本队列及已有账本探测 |
| reconciliation/history | Git blob 与权限保真、历史快照和未发布净增量 |
| reconciliation/records | 整批预检、版本渲染与记录提交 |
| reconciliation/evidence、objects | 外部检查范围与对象归属核对 |
| reconciliation/finish | 原发布原语组合、平台核验与可恢复 cleanup |
| workspace/reconcile_channel | CLI 与 audit-push 共用的逐提交输入边界 |

聚合和发布复用 closeout_render、merge_guard、pull_finish、pull_watch 与 tag_release。
standard 路径继续使用原交付账本；新路径不伪造历史 delivery/objectives/report。
