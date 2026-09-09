# CodeWiki Update

不要求已初始化 `.mdf/manifest.yaml`。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check entry                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────> [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Check standard                 │
└────────────────┬─────────────────┘
                 │
                 ├──── 缺失或为空 ────> [要求 codewiki generate]
                 ├──── 非空且不 standard ────> [列出不符合项并停止]
                 │
                 ▼ standard
┌──────────────────────────────────┐
│ 3 Analyze                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败 ────> references/codewiki-recovery.md
                 │
                 ▼ 分析成功
┌──────────────────────────────────┐
│ 4 Check changes                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 无代码变化且关闭后验收通过 ────> [报告已最新并结束]
                 ├──── 关闭或验收失败 ────> references/codewiki-recovery.md
                 │
                 ▼ 存在代码类变化
┌──────────────────────────────────┐
│ 5 Map modules                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 不可映射或需删页 ────> references/codewiki-recovery.md
                 │
                 ▼ 可映射且无需删页
┌──────────────────────────────────┐
│ 6 Update pages                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败 ────> references/codewiki-recovery.md
                 │
                 ▼ 写入成功
┌──────────────────────────────────┐
│ 7 Review hacks                   │
└────────────────┬─────────────────┘
                 │
                 ├──── 需删页或其他失败 ────> references/codewiki-recovery.md
                 │
                 ▼ 无需删页且验收通过
┌──────────────────────────────────┐
│ 8 Close and verify               │
└────────────────┬─────────────────┘
                 │
                 ├──── 关闭前后验收通过 ────> [报告并结束]
                 ├──── 失败 ────> references/codewiki-recovery.md
```

## 工作流（唯一执行契约）

完整读取 `references/common.md` 与 `references/codewiki-contract.md`。
入口执行 `references/codewiki-runtime.md`；失败恢复或重建时读取
`references/codewiki-recovery.md`，传入失败步骤、写入记录、session ID 与实际 workspace。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 入口 | 约束 | [检查 Git 与 MCP](#s1) | Git 根、工具可用 | 2 | 停止 |
| 2 | 目录 | 约束 | [检查 standard](#s2) | 有效 Wiki | 3 | 按目录状态停止 |
| 3 | 分析 | 脚本 | [读取完整 changes](#s3) | 变更分类 | 4 | 失败恢复 |
| 4 | 变化 | 约束 | [判断是否需更新](#s4) | 分类、关闭后 diff | 无变化结束；否则 5 | 失败恢复 |
| 5 | 映射 | 约束 | [检查映射与删页](#s5) | 影响及级联范围 | 6 | 重建流程 |
| 6 | 页面 | 脚本 | [最小修订并刷新](#s6) | 受影响文件 | 7 | 失败恢复 |
| 7 | 特殊实现 | 脚本 | [重审 hack 与链接](#s7) | 证据、页面一致 | 8 | 删页走重建；否则恢复 |
| 8 | 验收 | 脚本 | [关闭并验证输出](#s8) | 基线、事实、diff | 报告并结束 | 失败恢复 |

## 术语与数据结构

### 执行约束

下列明细补充表中操作、证据与异常处理；步骤顺序和跳转只由上表规定。

<a id="s1"></a>

**入口**

解析 `REPO_ROOT`、检查 CodeWiki MCP。

验收：Git 根、MCP。

异常与交接：工具缺失时按 runtime 流程配置后停止；Git 检查失败则直接停止，不写目标仓库。

<a id="s2"></a>

**目录**

按契约检查 `docs/repowiki/`。

验收：MDF CodeWiki standard。

异常与交接：目录缺失或为空时要求 `$mdf codewiki generate`；非空但不 standard 时列出缺失/损坏项并停止， 不调用
`analyze_repo`、不写入、不尝试修复。旧 Wiki 只可在用户移出受管根后作为只读 reference。

<a id="s3"></a>

**分析**

调用 `analyze_repo`，固定 `repo_path` 为 `REPO_ROOT`，`output_dir` 为 `REPO_ROOT/docs/repowiki`；读取返回的
`changes` 与 workspace 的完整 `changes.json`。

验收：变更分类。

<a id="s4"></a>

**变化**

`no_changes: true` 或仅手工文档变化时，确认本次未成功写入或编辑页面，调用 `close_session`。

验收：无代码、配置、schema、测试或已跟踪生成物变化；关闭后 Wiki diff 为空，
本次 workspace 已清理。关闭或验收失败进入 recovery，不得落入代码更新分支。

仅分类确定存在代码类变化时进入步骤 5；无变化且关闭后验收通过才报告已最新。

<a id="s5"></a>

**映射**

确认变化可映射到既有 `module_tree.json`，且不需删受管页。

验收：affected/cascade modules。

异常与交接：进入 recovery 流程，确认仓外备份并移出旧 Wiki 后交接重建。 MCP-only 契约不得用 shell 或编辑器删除、
重排或补写受管 Wiki。

<a id="s6"></a>

**页面**

为 affected modules 读取源码与关联文件，以 `edit_doc_file` 最小修订， 只有新页用 `write_doc_file`；
随后刷新 cascade 父页，最后更新 overview 的地图、 关系和链接。

验收：仅受影响的写入文件。

异常与交接：保留现场并进入 recovery 流程。

<a id="s7"></a>

**特殊实现**

重审 hack：存在至少一个可证 hack 且无页时 `write_doc_file`，有页时 `edit_doc_file`；
没有 hack 且无页时跳过写入；首次新建时同步在 `overview.md` 加入链接。

验收：hack 与 overview 一致。

异常与交接：需删整个 `hacks.md` 时进入 recovery 流程，确认备份并移出后交接重建。保持受管 marker、简体中文、
可证事实与 Mermaid 验证；
仓外事项省略或标明不覆盖。

<a id="s8"></a>

**验收**

关闭前先验收全部受影响页面、链接、事实与 Mermaid，未通过则进入 recovery，
不得推进基线。通过后调用 `close_session`；关闭后验收仅改 `docs/repowiki/`，受影响/级联页、overview、 链接、
模块树、metadata 一致，
`.codewiki/` 无仓库改动，无 TODO、待确认或未验证图； 抽样对照变更前后代码。

验收：更新基线、验证和 diff。

通过条件：报告检测方法、影响/级联模块、写入文件、hack 变化、验证和 diff，复查并提交本次 Wiki 改动。异常与交接：
停止并报告。

分析开始后的工具失败或验收失败统一进入 recovery；页面可修复时按其规则返回失败步骤。
