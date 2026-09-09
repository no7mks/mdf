# CodeWiki Generate

不要求已初始化 `.mdf/manifest.yaml`。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check entry                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Check output                   │
└────────────────┬─────────────────┘
                 │
                 ├──── standard ─────────────→ [要求 codewiki update]
                 ├──── 非空且非 standard ────→ [列出不符合项并停止]
                 │
                 ▼ 目录缺失或为空
┌──────────────────────────────────┐
│ 3 Analyze                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败 ────→ references/codewiki-recovery.md
                 │
                 ▼ 分析成功
┌──────────────────────────────────┐
│ 4 Write modules                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 可修复的图失败或跳过 ────→ 4 Write modules
                 ├──── 其他失败 ────────────────→ references/codewiki-recovery.md
                 │
                 ▼ 页面及图验收通过
┌──────────────────────────────────┐
│ 5 Close session                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败 ────→ references/codewiki-recovery.md
                 │
                 ▼ 关闭前验收通过且基线有效
┌──────────────────────────────────┐
│ 6 Verify output                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 全部验收通过 ────→ [报告并结束]
                 └──── 失败 ────────────→ references/codewiki-recovery.md
```

## 工作流（唯一执行契约）

表中操作与证据按下方同名条目核对；顺序与跳转只由本表规定。

完整读取 `references/common.md` 与 `references/codewiki-contract.md`。
入口执行 `references/codewiki-runtime.md`；失败恢复或重建时读取
`references/codewiki-recovery.md`，传入失败步骤、写入记录、session ID 与实际 workspace。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 约束 | 核对 Git 根并执行 runtime 工具检查 | 目标根、八工具可用 | 2 | 停止 |
| 2 | 目录 | 约束 | 核对 Wiki 目录不存在或为空 | 目录检查结果 | 3 | 按目录状态停止 |
| 3 | 分析 | 脚本 | MCP 分析，保存模块树并读取处理顺序 | 模块树、处理顺序 | 4 | 失败恢复 |
| 4 | 模块 | 脚本 | 按 leaf 到父页生成模块页，核对事实与图 | 页面、链接、图校验 | 5 | 修复后 4；否则失败恢复 |
| 5 | 基线 | 脚本 | 写 overview，关闭前验收通过才关闭会话 | 有效 metadata | 6 | 失败恢复 |
| 6 | 验收 | 约束 | 核对输出及 workspace，报告并复核提交 | 内容、范围、diff | 报告并结束 | 失败恢复 |

## 术语与数据结构

### 入口与目录

<a id="s1"></a>

**入口**

解析目标 Git 根 `REPO_ROOT` ；检查 CodeWiki MCP。

验收：Git 根与 MCP 可用。

异常与交接：工具缺失时按 runtime 流程配置后停止；Git 检查失败则直接停止， 不写 `docs/repowiki/`。

<a id="s2"></a>

**目录**

检查 `docs/repowiki/`：不存在或为空才可生成。

验收：目录状态。

异常与交接：standard 时要求 `$mdf codewiki update`，非空非 standard 时列出不符合项并停止。
用户可移至自选非受管位置后重调；旧材料只作 reference，代码优先。

### 模块与页面

<a id="s3"></a>

**分析**

调用 `analyze_repo`，固定 repo/output 路径，遵守 `.gitignore` 并按实际排除第三方和纯生成目录；
读取 workspace 的四个 JSON、`get_prompt(cluster)` 与所需 `read_code_components`；按内聚、调用与目录边界聚类，
使用原始 component ID 调用 `save_module_tree` 并读取 `processing_order.json`；小仓库不强造层级，
大仓库 避免只按目录机械切分。

验收：模块树和处理顺序。

异常与交接：保留现场并进入 recovery 流程。

<a id="s4"></a>

**模块**

按 processing order 先 leaf 后父模块；每页先 `get_prompt`，读取相关组件和必要文件，再用 `write_doc_file`
写入受管 marker、可证当前事实、职责、关系、边界与链接。

验收：模块页与 Mermaid 校验。

异常与交接：失败或跳过时修复或删图后重试。 对可读疑点追踪至事实；仓外事项省略或标为“不覆盖”；
不得遗留 TODO、待确认或猜测。 主动查找符合定义的 hack；存在才写 `hacks.md`，
不得将项目特定版本、迁移或路由 分层抽象成通用 hack 规则。

### 基线与输出验收

<a id="s5"></a>

**基线**

写入带受管 marker 的 `overview.md`，包含入口、地图、主要关系、阅读顺序及全部模块/hacks 链接。
关闭前先验收全部页面、链接、模块树、事实与 Mermaid；未通过则进入 recovery，
不得推进基线。通过后调用 `close_session`，随后进入步骤 6 检查实际基线和 workspace。

验收：至少一页 Markdown 写入后的 `metadata.json` 基线。

异常与交接：保留现场并进入 recovery 流程。

<a id="s6"></a>

**验收**

验收本次改动仅在 `docs/repowiki/`，overview、模块页、三个 JSON、链接、 模块树和 metadata 均有效且 `.codewiki/`
无仓库改动；抽样回读并对照代码确认简体中文、事实闭合、无占位，且所有 hack 符合定义。

验收：验证与 diff。

通过条件：报告模块数、 页面、hack 数、变更基线、验证结果和 diff，复查并提交本次 Wiki 改动。异常与交接：用 MCP 修复，
保留失败现场和 findings。

分析开始后的工具失败或验收失败统一进入 recovery；页面可修复时按其规则返回失败步骤。
