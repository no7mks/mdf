---
change_kind: "{{MDF_CHANGE_KIND}}"
source_branch: "{{MDF_SOURCE_BRANCH}}"
proposals: []
fixed: []
closed: []
deferred: []
adrs: []
# 按 references/changelog-writing.md 选 Added/Changed/Deprecated/Removed/Fixed/Security
# 纯文档、未实施提案或内部测试/CI 变更写 release_notes: none
release_notes:
  Changed:
    - "{{MDF_RELEASE_NOTE}}"
breaking: false
evidence:
  tests:
    - "{{MDF_TEST_PATH}}"
  commands:
    - "{{MDF_RERUNNABLE_COMMAND}}"
  artifacts: []
---

# Change

## 结果

{{MDF_DELIVERED_RESULT}}

## 已更新的当前文档

- {{MDF_UPDATED_CURRENT_FACT_PATH}}

## 已知偏差

无。
