# 发布目标

工作线按是否联调二选一，开分支前必须选定。fact update 由 finish 前段执行；已有有效结果则不重做。

- 不联调：`start → 开发 → verify → code-review → fact update → finish`
- 联调：`start → 开通道 → 对齐计划 → 本端验收 → 双端验收 → 确认无更多代码修改后 → code-review → fact update → finish`

## 本版范围

{{MDF_RELEASE_SCOPE}}

## 明确不含

{{MDF_RELEASE_EXCLUSIONS}}

## 联调

{{MDF_RELEASE_INTEGRATE}}

## 预发布工作

{{MDF_PRERELEASE_WORK}}

## 允许在本分支改什么

{{MDF_RELEASE_ALLOWED_CHANGES}}

## 可验证验收

{{MDF_RELEASE_ACCEPTANCE}}
