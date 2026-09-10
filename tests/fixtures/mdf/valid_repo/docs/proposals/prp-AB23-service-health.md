---
id: prp-AB23
type: proposal
status: ready
depends_on: []
---

# Service health

## 问题

调用方无法确定服务模块是否正常。

## 期望结果

调用方能取得稳定的健康状态。

## 范围

### 包含

- 提供布尔状态。

### 不包含

- 不提供远程监控。

## 验收标准

- `healthy()` 返回 `true`。
