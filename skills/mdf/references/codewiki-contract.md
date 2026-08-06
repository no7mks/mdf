# CodeWiki Wiki 契约

## 边界

- 仅用 CodeWiki MCP 的八个工具生成或修改 Wiki：
  `analyze_repo`、
  `read_code_components`、`write_doc_file`、`edit_doc_file`、
  `save_module_tree`、`get_processing_order`、`get_prompt`、`close_session`。
- 不运行 CodeWiki CLI、`generate_docs` 或 `get_module_tree`，不配置
  provider、model 或 API key。Agent 负责理解与写作；MCP 负责分析和受控写入。
- 不修改业务代码、配置、测试或 `docs/repowiki/` 以外的文档。不要自动
  commit。
  `docs/repowiki/` 之外的 `docs/` 仍由项目的普通人工文档契约管理。
- 生成内容使用简体中文。代码、路径、标识符和必要的术语可保留原文。

## CodeWiki MCP

先检查本次会话已启用八个 MCP 工具。若没有启用，安装或修复运行时，但不要开始
生成。仅在安装目录不存在时执行 clone；其余安装命令只在缺少相应运行时时执行：

```bash
CODEWIKI_DIR="$HOME/.local/share/codewiki"
git clone https://github.com/FSoft-AI4Code/CodeWiki.git "$CODEWIKI_DIR"
python3 -m venv "$CODEWIKI_DIR/.venv"
"$CODEWIKI_DIR/.venv/bin/python" -m pip install -e "$CODEWIKI_DIR"
"$CODEWIKI_DIR/.venv/bin/python" -c \
  'from codewiki.mcp.server import server'
```

目录已存在时不得 `git pull`、覆盖或清理它；仅在需要时补建 `.venv`、安装并
验证。若已有源码不完整、不可导入或工作树不干净，报告问题并停止。将下列配置加入
宿主 IDE 的 MCP 设置，要求用户启用 server 后重新显式调用 intent：

```json
{
  "mcpServers": {
    "codewiki": {
      "command": "/absolute/path/to/CodeWiki/.venv/bin/python",
      "args": ["-m", "codewiki.mcp.server"],
      "cwd": "/absolute/path/to/CodeWiki"
    }
  }
}
```

安装目录和 IDE 配置不属于目标仓库产出。MCP workspace 可能暂存于目标仓库
`.codewiki/`；必须由 `close_session` 清理，最终不得留下或忽略该目录。动态启用
MCP 后不得假定当前 Agent 会话已经获得工具；必须重新调用。缺任何必需工具时，只
报告配置步骤，不写目标仓库。

## 受管输出

唯一受管根目录是 `docs/repowiki/`，并应提交到 Git：

```text
docs/repowiki/
├── overview.md
├── <module>.md
├── hacks.md                 # 仅在发现至少一个 hack 时存在
├── first_module_tree.json
├── module_tree.json
└── metadata.json
```

`module_tree.json` 是当前模块树，`first_module_tree.json` 是首次聚类快照；
`metadata.json` 由 `close_session` 写入增量基线。`overview.md` 与每个受管
Markdown 都以以下首行开始：

```markdown
<!-- mdf-codewiki: managed; do not edit manually -->
```

这三份 JSON 均须存在且可解析；`metadata.json` 的
`generation_info.commit_id` 和 `generation_info.timestamp` 均非空。所有受管
Markdown 都由 CodeWiki MCP 写入或编辑，不接受人工直接修改，也不设置
annotation、overlay 或人工二级目录。

符合上述目录、三个 JSON、首行 marker 和基线字段的根目录才是
`MDF CodeWiki standard`。任何缺项、损坏 JSON、空基线、未标记 Markdown 或其他
既有 Wiki 都是非标准目录，不得用增量更新覆盖。

## 写作与事实

- 以当前 checkout 的代码、配置、schema、测试和已跟踪生成物为证据。已有手工文档
  或旧 Wiki 只可辅助定位，不可覆盖代码证据。
- 能由本仓查证的行为必须读完并写成事实；不得用“待确认”、TODO 或猜测代替阅读。
  矛盾实现如实说明条件和位置。
- vendor 内部、环境密钥实际值、线上调用方或其他仓外事实不属于本 Wiki；按需要省略，
  或明确写“本 Wiki 不覆盖”。
- 每个模块页说明职责、关键组件、调用或数据关系、边界与仓库相对证据。先处理 leaf，
  再处理父模块；所有交叉链接必须可解析。
- 只在 Mermaid 校验成功时保留图。校验失败或跳过时，修复运行时或删除该图，不得称其
  已校验。

## Hack 收录

`hack` 是本仓可证的特殊实现：它偏离同类功能的普通路径、公开接口契约或预期约束，
且省去该特殊处理会改变行为。它不是笼统的“旧代码”，也不预设版本、迁移、路由或
其他项目专属类别。

发现一个或多个 hack 时，创建 `hacks.md` 并从 `overview.md` 链接。每项至少写明：
位置、触发条件、实际行为、所偏离的普通规则、可见影响和代码证据。无证据时不收录；
没有 hack 时不创建空页。
