---
id: req-01arz3ndektsv4rrffq69g5fav
type: requirement
status: ready
related: []
---

# Service health

## Problem

调用方无法确定服务模块是否正常。

## Desired Outcome

调用方能取得稳定的健康状态。

## Scope

### In

- 提供布尔状态。

### Out

- 不提供远程监控。

## Acceptance Criteria

- `healthy()` 返回 `true`。
