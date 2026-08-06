# CodeWiki Update

不要自动 commit。完整读取 `intents/common.md` 与
`references/codewiki-contract.md`。

## 1. 标准门禁

1. 解析目标 Git 根 `REPO_ROOT`，在外层 intent 入口检查 clean worktree。此
   intent 不要求 `.mdf/manifest.yaml` 已初始化。
2. 检查 CodeWiki MCP 是否可用。缺工具时按契约安装、给出 MCP 配置并停止；不要写
   目标仓库。
3. 按 CodeWiki 契约检查 `docs/repowiki/`。目录不存在时，要求
   `$mdf codewiki generate`；目录非空但不符合 MDF CodeWiki standard 时立即拒绝更新，
   不调用 `analyze_repo`、不写文件、不尝试修复。
4. 报告缺失或损坏的标准项，并要求显式新建 `$mdf codewiki generate`。旧
   `repowiki` 只可在用户移出受管根后作为只读 reference；不得把它当成可更新的基线。

## 2. 变更判定

1. 调用 `analyze_repo`，固定 `repo_path` 为 `REPO_ROOT`、`output_dir` 为
   `REPO_ROOT/docs/repowiki`，并读取返回的 `changes` 与 workspace 中的完整
   `changes.json`（如有）。
2. `no_changes: true` 时调用 `close_session`，不写任何文件，报告 Wiki 已是最新。
3. 仅手工文档变更而没有代码、配置、schema、测试或已跟踪生成物变化时，同样关闭
   会话且不写 Wiki。手工文档可以辅助阅读，但不是独立更新触发器。
4. 若变更不能映射到既有 `module_tree.json`，或需要删除受管页面，停止并报告需要
   新的 generate 基线。MCP-only 契约不允许用 shell 或编辑器删除、重排或补写受管
   Wiki。

## 3. 增量写入

1. 对 `affected_modules`，读取新组件源码与关联文件；使用 `edit_doc_file` 做最小、
   可定位的事实修订。仅不存在的新页面才使用 `write_doc_file`。
2. 对 `cascade_modules`，在子页更新后刷新父页；最后更新 `overview.md` 的地图、
   关系和链接。不要重写不受影响的模块，也不要把增量更新退化为全量生成。
3. 重新审查受影响区域是否出现、变化或消失了 hack。`hacks.md` 不存在时用
   `write_doc_file` 新建；存在时用 `edit_doc_file` 修订。若需要删除整个
   `hacks.md`，按上节停止并要求新基线。首次创建时，无论是否属于
   `cascade_modules`，都要同步用 `edit_doc_file` 在 `overview.md` 加入链接。
4. 保持受管 marker、简体中文、可证事实和 Mermaid 验证。能够从本仓闭合的事项必须
   闭合；仓外事项按契约省略或标明不覆盖。

## 4. 收尾与验收

1. 调用 `close_session`，确认 `metadata.json` 的基线已更新。写入失败时保留现场并
   报告。
2. 验收改动只在 `docs/repowiki/`；受影响页、级联页、overview、链接、模块树和
   metadata 均一致，且 `.codewiki/` 不残留为仓库改动。不得遗留“待确认”、TODO 或
   未经验证的 Mermaid 图。
3. 抽样对照变更前后代码与更新页，确认没有扩大到不受影响模块。报告检测方法、影响
   模块、级联模块、写入文件、hack 变化、验证结果和 diff；提醒用户复查并自行提交。
