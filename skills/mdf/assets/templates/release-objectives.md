# 发布目标

## 流程

- needs_design: {{MDF_NEEDS_DESIGN}}

## 步骤

依赖链由上到下；完成一项由对应 intent **自勾** `[x]`。
进度只认本清单，不以 `gates/*.json` 或 verify/fact 报告当通行证。

- [ ] 确认工作线与范围（start）
- [ ] design（仅 needs_design: yes；由 `$mdf design` 自勾）
- [ ] 完成预发布工作（owner；可与 design 后的开发合并勾选）
- [ ] owner 开发（仅 needs_design: no 或无并行角色时）
- [ ] converge（objectives 前置已勾 + on-site；由 `$mdf converge` 自勾）
- [ ] code-review（由 `$mdf code-review` 自勾；报告见 code-review.md）
- [ ] verify full（由 `$mdf verify` full 自勾；报告见 verify.full.json）
- [ ] fact audit（由 `$mdf fact audit` 自勾；必要时先 fact update）
- [ ] close-out（由 `$mdf close-out` 自勾）

## 工作线

{{MDF_RELEASE_WORK_LINE}}

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
