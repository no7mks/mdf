# 发布目标

## 本版范围

{{MDF_RELEASE_SCOPE}}

## 工作线

{{MDF_RELEASE_WORK_LINE}}

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

## 流程

- needs_design: {{MDF_NEEDS_DESIGN}}
- has_dev: {{MDF_HAS_DEV}}

`has_dev` 仅表示是否有计划内 owner 开发阶段；`no` 仅跳过 owner 开发与 converge。
后续 code-review、verify 等阶段仍可为本版目标修复代码，按对应阶段复审与验证。
修复不因此改写 `has_dev` 或补走 converge。

## 步骤

依赖链由上到下；完成一项由对应 intent **自勾** `[x]`。
联调例外：integrate 先打开工作线，内部完成适用的 design / 开发 / converge 后验收、冻结并自勾。
这些开发阶段不依赖 integrate 已勾；code-review 仍须等联调收口。
进度只认本清单，不以 `gates/*.json` 或 verify/fact 报告当通行证。
github-flow 发布分支由 start 在 consolidate 后加入 publish。清单完成后按实际 Git 状态进入 merge/pr 与收尾。
跳过项由 start 写入时即勾为 `[x]`（不靠缺席表示跳过）。

- [ ] 确认工作线与范围（start）
- [ ] integrate（无联调工作线：start 写入时已勾；其余模式：由 `$mdf integrate` 自勾）
- [ ] design（仅 needs_design: yes；由 `$mdf design` 自勾）
- [ ] 完成预发布工作（owner；无预发布事务时 start 写入时已勾）
- [ ] owner 开发（has_dev: no：start 写入时已勾；has_dev: yes：owner 完成后自勾）
- [ ] converge（has_dev: no：start 写入时已勾；has_dev: yes：由 `$mdf converge` 自勾）
- [ ] lint（由 `$mdf lint` 自勾）
- [ ] code-review（由 `$mdf code-review` 自勾；报告见 code-review.md）
- [ ] verify branch（由 `$mdf verify` branch 自勾；报告见 verification-report.json）
- [ ] fact audit（由 `$mdf fact audit` 自勾；必要时先 fact update）
- [ ] catch-up（同步远端同名分支并增量验收）
- [ ] consolidate（收敛交付文档与对象记录）
