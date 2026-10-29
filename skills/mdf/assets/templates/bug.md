---
id: "{{MDF_BUG_ID}}"
type: bug
status: open
severity: major
found_in: {{MDF_FOUND_IN}}
---

# {{MDF_TITLE}}

## 观察到的行为

{{MDF_OBSERVED_BEHAVIOR}}

## 期望行为

{{MDF_EXPECTED_BEHAVIOR}}

## 复现步骤

1. {{MDF_REPRODUCTION_STEP}}

## 影响

{{MDF_IMPACT}}

## 所需回归证据

{{MDF_REQUIRED_REGRESSION_EVIDENCE}}

### 关联 failing tests

{{MDF_FAILING_TEST_ASSOCIATIONS}}

<!-- 默认至少一条，可复用或新增；每条记录 module、文件、精确 test ID、命令、退出状态与失败证据。
同时记录正常 suite 成员关系及 active/removed/restored 状态；移除时补齐排除位置和恢复方式。
仅用户明确确认后允许写“关联 failing tests: []”，并记录原因、确认时间与确认内容。 -->
