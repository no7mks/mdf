# Tree

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check repo                     │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Run CLI                        │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止并报告]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 3 Render tree                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ─────────→ [结束]
                 └──── 失败/缺失 ────→ [停止并报告]
```

## 工作流（唯一执行契约）

读取 `references/common.md` 与 `references/object-contract.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check repo | 约束 | 解析目标根与 depth，要求 ready | 目标根、depth | 2 | 停止并报告 |
| 2 | Run CLI | 脚本 | 运行 tree CLI | 退出状态、依赖视图 | 3 | 停止并报告 |
| 3 | Render tree | 约束 | 画出按 milestone 分组的混态树与索引 | 树、索引、hidden | 结束 | 停止并报告 |

`$mdf tree`、`$mdf prp tree`、`$mdf next?` 与 `$mdf next？` 执行本流程；
也可由 next 在无在途时内部委托。可带 `--depth N`。

## 术语与数据结构

### 入口与计算

只读，不要求 clean worktree，不创建或拆分 PRP。
运行 `python3 "$MDF_ROOT/scripts/mdf.py" tree --repo "$REPO_ROOT" --depth <N>`；
默认 3，N 为正整数。要求 `manifest` ready；参数非法或仓库未就绪时报告原因
和所需操作，不自动初始化。depth 只截断展示，不改变依赖判定。
implemented/released 依赖视为满足；milestone 依赖在该阶段不存在 draft 或
ready PRP 时满足。非法依赖停止，不输出误导性树。空结果明确说明无 draft
且无 ready。不选择 MVP、不发现新需求、不因 draft 自动启动 prp review。

### 展示

先输出图例，再按 CLI `trees` 顺序画按 milestone 分组的 unicode 混态树，
最后输出索引与 hidden。组头不计入 depth。

图例固定为：`● ready`、`○ draft`、`* in_progress`、`↩ 交叉引用`、
`[milestone]`、`↑ 上一组 milestone`。

树含全部 draft 与 ready。根为 `blocked_by` 中没有 active PRP ID 的节点。
`trees` 已按组序给出：无 milestone 依赖的无归属根在前；有归属的根按
milestone 分成组，被依赖的组在上，依赖它的组在下；并列按名，组内按
PRP ID。无归属根不写组头；其余每组先写组头 `[<值>]`，再画该组的根。

子节点只挂在 `blocked_by` 里的 active PRP 下。milestone 名画成组头，
不画成 PRP 节点；依赖它的 PRP 不挂到其成员下。重复节点第一次展开，
其后用 `↩ <id>` 并保留全部 `blocked_by`。`in_progress` 在标题后标 `*`。
组内节点省略与组头相同的 `[<值>]`；嵌套子节点与父相同时也可省略，
不同则仍写。

后一组若有根的 `blocked_by` 含上一组 milestone 名，在两组之间最左列
单写 `↑`，从该根的树干直接向上接到上一组；不要画成子节点。指向非
上一组的未满足 milestone 时，在该根最左列写 `↑ <name>`。相邻但无
milestone 依赖的组不加箭头。截断层不画，只报 `hidden`。树的下游不
表示完成一个上游即可开工。

```text
[m4-py-session]
○ prp-043 driver 契约
├ ○ prp-044 session init
│ └ ○ prp-045 记忆迁入
└ ↩ prp-045 ← prp-043, prp-044
[m5-client-on-py]
○ prp-037 会话状态
└ ○ prp-003 crush-client 契约
○ prp-038 memory_sync
└ ↩ prp-003 + prp-037, prp-038
↑
[m99-cutover]
○ prp-004 正式部署与切流
```

索引按 milestone 分组，无归属另列；每项含 id、title、status、
`depends_on`、`blocked_by` 与 `in_progress`。
