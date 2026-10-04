# 人工 feature

`$mdf start --manual` 按 feature 处理，不绑定 PRP；`delivery.json` 写入 `manual: true`。
本页规定人工 feature 的主线；普通交付的 design、开发与 converge 规则不适用。

- start 通过 clarify 与用户确认工作范围及 slug。
  先询问，再给 slug 建议并取得确认。
- 从 develop 创建 `feature/<slug>` 与独立 owner worktree；roster 固定为 `0,0,1`。
- objectives 使用 `assets/templates/manual-objectives.md`。
  - 顺序：start → 人工工作 → code-review → verify smoke → fact update → close-out。
- start 自勾 start；人工工作仅由用户显式勾选，Agent 不得代勾。
  - 用户可要求 Agent 介入实现与测试；介入不代表人工工作已完成。
  - next / deliver 在人工工作未勾时交接给用户；auto-pilot / yolo 同样不得代勾或越过。
  - 用户显式勾选后，由 next 单步续办或 deliver 串联剩余阶段。
- code-review 用 1 个 reviewer；前置为人工工作已勾，不要求 converge。
- verify smoke 执行 feature 的 branch 验证（lint/build/quick/smoke），
  写入 `verification-report.json`；通过后自勾 verify smoke。
- fact update 直接对齐当前事实，沿用其内部审阅与验证，通过后自勾 fact update。
- close-out 核对上述前置项及报告；不要求 design、converge 或独立 fact audit 项。
  - Change 的 `proposals: []`；无 PRP 状态更新。
  - 沿用 feature 的 no-ff 合入 develop、源分支删除及 worktree 保留规则。
