# CodeWiki Generate

不要自动 commit。完整读取 `intents/common.md` 与
`references/codewiki-contract.md`。

## 1. 入口与输出根

1. 解析目标 Git 根 `REPO_ROOT`，在外层 intent 入口检查 clean worktree。此
   intent 不要求 `.mdf/manifest.yaml` 已初始化。
2. 检查 CodeWiki MCP 是否可用。缺工具时按契约安装、给出 MCP 配置并停止；不要
   写 `docs/repowiki/`。
3. 检查 `docs/repowiki/`：目录不存在或为空时继续；符合 MDF CodeWiki standard
   时停止，要求改用 `$mdf codewiki update`；非空但不符合 standard 时停止，列出
   不符合项。不得覆盖、移动或删除旧 Wiki。
4. 用户可把旧 Wiki 移至自己选定的非受管位置后重新调用本 intent；那份材料可作为
   只读 reference，但代码证据优先。这个显式新建过程是旧 `repowiki` 的唯一迁移路径。

## 2. 分析与模块树

1. 调用 `analyze_repo`，固定 `repo_path` 为 `REPO_ROOT`、`output_dir` 为
   `REPO_ROOT/docs/repowiki`，遵守 `.gitignore`，按仓库实际情况排除第三方和纯
   生成目录。
2. 读取 MCP 返回的 workspace 中 `component_index.json`、`leaf_nodes.json`、
   `languages.json` 与 `summary.json`。调用 `get_prompt(cluster)`，再用
   `read_code_components` 读取形成模块判断所需的组件源码。
3. 按功能内聚、调用关系和目录边界聚类；小仓库不强造层级，大仓库避免只按目录机械
   切分。使用原始 component ID 调用 `save_module_tree`，读取其
   `processing_order.json`。

## 3. 生成模块页

1. 按 processing order 先处理 leaf 模块，后处理父模块。每页先调用相应
   `get_prompt`，再读取相关组件和必要的仓库文件。
2. 用 `write_doc_file` 写入模块页。首行加入受管 marker；内容只陈述可从本仓验证的
   当前结构与行为，说明组件职责、关系、边界和可访问的交叉链接。
3. 对可读出的疑点继续追踪到事实；仓外事项按契约省略或标明“不覆盖”。不得留下
   “待确认”、TODO、猜测或伪装为事实的计划。
4. 主动查找满足 hack 定义的特殊实现。发现时用 `write_doc_file` 创建 `hacks.md`；
   不发现时不得创建空页。不得把特定项目的版本、迁移或路由分层抽象成通用 hack
   规则。
5. 每次写入都检查 MCP 返回的 Mermaid 校验。失败或跳过时修复或删图，再继续。

## 4. 总览、收尾与验收

1. 用 `write_doc_file` 写入 `overview.md`，首行加入受管 marker。它必须说明仓库
   入口、模块地图、主要关系、阅读顺序，并链接全部模块页和存在的 `hacks.md`。
2. 调用 `close_session`。只有本次至少写入一份 Markdown 后它才会建立
   `metadata.json` 增量基线；缺失基线视为失败。
3. 验收输出范围：本次目标仓库改动只能位于 `docs/repowiki/`。验收所需的
   `overview.md`、模块页、三个 JSON、所有链接、模块树和 metadata 基线都必须有效；
   `.codewiki/` 不得残留为仓库改动。
4. 抽样回读页面并对照代码，确认中文、事实闭合、无未决占位，以及 hack 页中每项均
   满足定义。失败时在本次会话内用 MCP 修复，保留失败现场和 findings。
5. 报告模块数、页面列表、hack 数、使用的变更基线、验证结果和 diff；提醒用户复查并
   自行提交。
