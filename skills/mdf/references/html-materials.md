# HTML 工作材料

本页规定交付总结的 HTML 格式、信息完整性和展示检查。

## 格式与展示

HTML 是可独立打开的完整文档，正文必须放在唯一的 `<main>` 中。

- 使用 [深色终端文档模板](../assets/templates/document.html)。
  - 深色背景、浅绿章节、等宽文字、章节目录；窄屏目录换行，宽表与代码独立滚动。
- 把实际正文填入 `MDF_DOCUMENT_CONTENT`，标题填入 `MDF_DOCUMENT_TITLE`。
  - `MDF_DOCUMENT_OUTLINE` 为可见章节的锚点链接，必须与正文 `h2` 的 `id` 对齐。
- `html_documents.render_document(content, title)` 可从 HTML 正文生成完整文件。
- 使用 `<!doctype html>`、`lang="zh-CN"`、UTF-8、viewport 与可读的内嵌 CSS。
- 以标题、列表、表格和代码块组织信息；宽表与代码块允许滚动。
- 不依赖网络、外部字体或 JavaScript；离线打开也能阅读全部正文。
- 内容与 attribute 必须正确 escape；证据链接相对当前文件，外部链接保持原地址。
- 按 [写作规则](doc-structure.md) 复核 ASD-STE100 可适用原则。
  - 详细信息按主题展开，不以摘要代替正文；不得删去条件、例外、取舍或证据。
- HTML 不设文件行数上限；可见正文仍按写作规则检查结构。
- 展示前在宿主 browser / HTML preview 打开实际文件，检查标题、完整正文、表格和链接。
  - 无可用预览时报告限制并提供文件路径；不得声称已完成视觉检查。

## 设计与开发总结

每次 close-out 在 Gitflow 前留存 `delivery-summary.html`，按模板记录完整交付。

- 使用 [总结正文模板](../assets/templates/delivery-summary.html)，涵盖所有交付 kind 与人工 feature。
  - 填写实际内容后套用上述文档模板，保存完整 HTML；不得把正文 fragment 当作最终文件。
- feature / bugfix：`changes/unreleased/<slug>/delivery-summary.html`。
- release / SemVer hotfix：先写 `changes/unreleased/<semver>/delivery-summary.html`。
- slug hotfix：先写 `changes/unreleased/<slug>/delivery-summary.html`，归档后沿用版本目录。
  - `release-closeout` 随材料搬入 `changes/<semver>/delivery-summary.html`。
- feature / bugfix 的总结随 child Change 进入 `changes/<version>/<slug>/`。
  - HTML 链接由 CLI 随材料与对象 archive 改写；搬迁后核对链接仍有效。
- 每节使用实际结果、具体路径和理由；“完成开发 / 测试通过”不能替代完整记录。
- 内容要求如下；未执行的阶段明确写跳过原因，无法取得的历史证据如实标记缺失。

| 内容 | 必须记录 |
| --- | --- |
| 范围与结果 | 交付 kind、完整对象 ID、起点、目标、非目标、约束与实际验收结果 |
| 完整过程 | start、design、开发 / 测试、converge、审查、验证、hook、fact、close-out 的实际顺序 |
| 执行细节 | 参与者、并行分工、交接、失败、修复、重试、暂停与续办，以及阶段产物链接 |
| 设计决策 | 问题、候选、选择、理由、代价、确认依据；未采用方案与不需要 design 的理由 |
| 开发与测试 | 实现行为、关键路径、边界 / 错误处理、验收与 testcase 映射、未覆盖项 |
| 偏差与变更 | 计划与实际、原因、影响、接受记录、遗留风险、Bug / follow-up；无偏差也明确记录 |
| 审查与证据 | 各轮问题、裁定、修复复核、命令、suite、结果、报告路径与事实文档更新 |
| 收口与后续 | 集成 / 冲突处理、对象 outcomes、版本决策、目标分支 / tag / push 计划、后续事项 |

- Gitflow 前记录已完成过程与待执行收口；不得提前声称合并、tag 或 push 成功。
  - Gitflow 结果以实际命令及宿主最终报告为证据；总结链接 Change 和已有收口证据。
- 总结不替代 objectives 进度账本、当前事实文档、ADR 或测试报告。
- 主线前进或 bug close 导致补审补测时更新总结，再核对、提交并继续 Gitflow。
  - 已收口 release / hotfix 续办复用已归档总结，不覆盖已开始发布的源提交。
