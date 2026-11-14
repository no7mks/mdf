# Tree

树形：not-tree。此 intent 由一次 CLI 调用完成。

## 工作流（唯一执行契约）

读取 `references/common.md` 与 `references/object-contract.md`。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Run CLI | 脚本 | 传入目标目录与用户参数，原样转发 CLI 输出 | 退出状态、stdout 或 stderr | 转发 stdout 并结束 | 转发 stderr 并停止 |

`$mdf tree`、`$mdf prp tree`、`$mdf next?` 与 `$mdf next？` 执行本流程；
也可由 next 在无在途时内部委托。可带 `--depth N`。

## 术语与数据结构

### 入口与计算

本节规定 tree CLI 的参数来源与依赖判定。

- 只读，不要求 clean worktree，不创建或拆分 PRP。
- 运行 `python3 -B "$MDF_ROOT/scripts/mdf.py" tree --markdown --repo "$TARGET_DIR"`，
  将 intent 后的用户参数逐项作为 argv 追加，保留原顺序和值。
  - `TARGET_DIR` 取本次指定或当前绑定的目标目录，无绑定时用当前目录。
  - CLI 定位 Git 根，解析并验证参数。`--depth` 默认 3，N 为正整数。
  - depth 只截断展示，不改变依赖判定。
- CLI 要求 `manifest` ready。
- 依赖满足条件：
  - implemented/released 依赖视为满足。
  - milestone 依赖在该阶段不存在 draft 或 ready PRP 时满足。
- ❌ 非法依赖停止，不输出误导性树。
- 空结果明确说明无 draft 且无 ready。
- ❌ 不选择 MVP、不发现新需求、不因 draft 自动启动 prp review。

### 展示

CLI 的 stdout 是完整 Markdown，Agent 原样转发。

- tree 省略自身的阶段播报与结果摘要。宿主工作区横幅按公共规则输出。
- `diagram` 在 `text` 围栏中显示按 milestone 分组的 unicode 混态树。
  - 非空时含图例。组头不计入 depth。
- `table` 直接显示为 Markdown 索引表。
- 空结果的围栏内显示「无 draft 且无 ready。」，索引仍含表头与 `hidden:` 行。

图例固定为：`● ready`、`○ draft`、`* in_progress`、`↩ 交叉引用`、
`[milestone]`、`↑ 上一组 milestone`。

### 树的根与分组

树含全部 draft 与 ready。根为 `blocked_by` 中没有 active PRP ID 的节点。

- `trees` 已按组序给出：
  - 无 milestone 依赖的无归属根在前。
  - 有归属的根按 milestone 分成组，被依赖的组在上，依赖它的组在下。
  - 并列按名，组内按 PRP ID。
- 无归属根不写组头；其余每组先写组头 `[<值>]`，再画该组的根。

### 子节点

- 子节点只挂在 `blocked_by` 里的 active PRP 下。
- milestone 名画成组头，不画成 PRP 节点；依赖它的 PRP 不挂到其成员下。
- 重复节点第一次展开，其后用 `↩ <id>` 并保留全部 `blocked_by`。
- `in_progress` 在标题后标 `*`。
- 组内节点省略与组头相同的 `[<值>]`。
  - 嵌套子节点与父相同时也可省略，不同则仍写。

### 组间箭头与截断

- 后一组若有根的 `blocked_by` 含上一组 milestone 名：
  - 在两组之间最左列单写 `↑`，从该根的树干直接向上接到上一组；不要画成子节点。
- 指向非上一组的未满足 milestone 时，在该根最左列写 `↑ <name>`。
- 相邻但无 milestone 依赖的组不加箭头。
- 截断层不画，只报 `hidden`。
- ⚠️ 树的下游不表示完成一个上游即可开工。

### 索引

- 索引按 milestone 分组，无归属另列。
- 每项含 id、title、status、`depends_on`、`blocked_by` 与 `in_progress`。
- `table` 合成一张表，无归属行在前，其后按组；末行为 `hidden:` 加被截断 ID。
