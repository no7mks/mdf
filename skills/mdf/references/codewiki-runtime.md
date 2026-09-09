# CodeWiki Runtime

由生成、更新入口调用。完成配置后不在当前调用中生成 Wiki。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check tools                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 全部可用 ────> [返回调用方]
                 │
                 ▼ 缺少工具
┌──────────────────────────────────┐
│ 2 Check source                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 源码异常 ────> [报告并停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Prepare runtime                │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败 ────> [报告并停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 4 Configure host                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 配置失败 ────> [报告并停止]
                 ├──── 配置完成 ────> [要求启用后重新显式调用]
```

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 工具 | 约束 | 检查八工具 | 当前会话工具清单 | 返回调用方 | 缺工具到 2 |
| 2 | 源码 | 脚本 | [检查安装目录](#source) | 完整、干净源码 | 3 | 报告并停止 |
| 3 | 运行时 | 脚本 | [按缺项安装](#runtime) | 命令退出 0、可导入 | 4 | 报告并停止 |
| 4 | 配置 | 约束 | [配置宿主](#host) | 配置与用户启用说明 | 停止，要求重调 | 报告并停止 |

## 术语与数据结构

### 工具与源码

八工具由 `references/codewiki-contract.md` 列出；必须检查本次会话的实际可调用工具，
不能把磁盘安装成功当作工具已启用。缺任何工具时不写目标仓库。

<a id="source"></a>

安装目录为 `$HOME/.local/share/codewiki`。目录不存在才 clone；目录存在时先检查
源码完整、工作树干净，不得 pull、覆盖或清理已有目录。检查失败时报告具体问题。

```bash
CODEWIKI_DIR="$HOME/.local/share/codewiki"
git clone https://github.com/FSoft-AI4Code/CodeWiki.git "$CODEWIKI_DIR"
```

### 运行时与宿主配置

<a id="runtime"></a>

只在缺少相应运行时时补建 `.venv` 或安装；已有运行时无法导入时报告并停止。
每条安装命令成功后才运行下一条，最后以导入检查验收。

```bash
python3 -m venv "$CODEWIKI_DIR/.venv"
"$CODEWIKI_DIR/.venv/bin/python" -m pip install -e "$CODEWIKI_DIR"
"$CODEWIKI_DIR/.venv/bin/python" -c \
  'from codewiki.mcp.server import server'
```

<a id="host"></a>

将以下字段加入宿主 IDE 的 MCP 设置，保留其他配置；路径使用已确认的安装位置。
配置后要求用户启用 server 并重新显式调用 intent；不得假定当前会话已获得工具。

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
