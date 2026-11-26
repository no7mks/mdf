# 变更记录

## Unreleased

- 新增 `check` 四档静态检查。入口仅核对控制面。历史对象及 evidence 问题由写后与收口检查报告。
- 将常用静态检查迁至 `check`。IG 保留 `validate --level strict` 与 `fact audit --against <sha> --quick`。
- 事实审阅在本轮范围内复用收口静态规则。参考型主题叶可声明 `doc_style: reference`。
