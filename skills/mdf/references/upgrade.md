# Upgrade

`$mdf upgrade` 更新本机仓外 MDF。
除补齐仓库根 `.gitignore` 外，不修改业务仓，也不 push。

- 默认源为 `https://github.com/no7mks/mdf.git`。
- 版本目录在 `<安装根>/versions/<revision>/`。
- `current` 用一次原子替换切换。
- 自检失败时切回旧版本，并删除本次新建的目录。
- 已启动的调用继续使用原版本。
- 下一次调用才使用切换后的版本。

除根 SKILL.md 指定的横幅条款外，不读取 `references/common.md`。

## 决策树

```text
┌──────────────────────────────────┐
│ 1 Check tools                    │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 2 Preview fetch                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 失败/缺失 ────→ [停止]
                 │
                 ▼ 已得到预览
┌──────────────────────────────────┐
│ 3 Confirm replace                │
└────────────────┬─────────────────┘
                 │
                 ├──── 拒绝 ────────────────→ [结束]
                 ├──── 未决或非明确答复 ────→ 3 Confirm replace
                 │
                 ▼ 用户确认替换
┌──────────────────────────────────┐
│ 4 Apply replace                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 上游已变化 ────→ 2 Preview fetch
                 ├──── 自检失败 ──────→ [回滚并停止]
                 │
                 ▼ 通过
┌──────────────────────────────────┐
│ 5 Report result                  │
└────────────────┬─────────────────┘
                 │
                 ├──── 通过 ────────→ [结束]
                 └──── 无法展示 ────→ [停止]
```

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Check tools | 脚本 | 核对 `info` | 三个版本为 3、修订号 | 2 | 停止 |
| 2 | Preview fetch | 脚本 | launcher `upgrade --dry-run` | `new_commit` 与 `history` | 3 | 停止 |
| 3 | Confirm replace | 约束 | 展示提交摘要并取得明确确认 | 用户确认 | 4 | 拒绝则结束；未决留在 3 |
| 4 | Apply replace | 脚本 | 绑定确认 commit 后安装 | `current` 指向新修订 | 5 | 源变化回 2；自检失败则回滚 |
| 5 | Report result | 约束 | 报告修订号；有副本时建议 detach | 摘要 | 结束 | 无法展示则停止 |

### 预览

```bash
python3 -B "$MDF_ROOT/scripts/mdf_launcher.py" upgrade --dry-run
```

有其他源时追加 `--source <url>`。

- 输出含 `source`、`new_commit`、`revision` 与 `history`。
- `history.status` 不为 `ok` 时说明原因，不得编造提交。
- 预览不切换 `current`。

### 替换

```bash
python3 -B "$MDF_ROOT/scripts/mdf_launcher.py" upgrade --expected-commit <步骤2确认的new_commit>
```

- 必须传入预览确认的完整 commit。
- 上游 HEAD 变化时返回 `upgrade_source_changed`，回到预览。
- 新版本的入口执行安装。旧 Core 损坏时仍可升级。
- 自检失败则回滚，不留下半更新的 `current`。
- ❌ 不修改业务仓的 `.mdf/`、`docs/` 或 Skill 副本。不 push。

### 报告

报告旧修订、新修订和 `history` 摘要。

- 下一次 `$mdf` 调用按新版本执行。
- 已启动的调用不改用新版本。
- 当前目录是 Git 仓库，且仍跟踪 `.<host>/skills/mdf` 时，建议 `mdf detach --repo <仓库>`。
- detach 只删除那六处副本，并提交 `chore(mdf): 移除仓内 MDF Skill 副本`。
- ❌ detach 不得删除 `.mdf/` 或 `docs/`。

## 契约切换

只有破坏性契约变更才改业务仓的 `schema_version`。

```bash
python3 -B "$MDF_ROOT/scripts/mdf.py" contract-switch --repo "$REPO_ROOT"
```

- 仓库须 clean，且当前分支是 workflow trunk。
- 只改 manifest 里 `schema_version` 那一行。
- 声明值高于本机契约时失败，并提示 `mdf upgrade`。
- PR mode 在 `codex/contract-switch` 提交。其他模式在 trunk 提交。
- 不跑 doctor、idle 或其他门禁。

声明值低于本机工具时，先 contract-switch，再继续 migrate。
规则见 [contract-switch](contract-switch.md)。
