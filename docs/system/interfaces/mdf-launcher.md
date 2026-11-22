# 仓外 MDF 入口

业务仓不保存 MDF 本体。本机用版本目录提供脚本、协议和模板。

## 安装根

| 条件 | 行为 |
| --- | --- |
| `MDF_HOME` 已设置且 `current` 有效 | 使用该安装根 |
| `MDF_HOME` 为空，或 `current` 无效 | 报错并停止，不回退 |
| `MDF_HOME` 未设置 | 使用 `~/.local/share/mdf` |

两处都有效时，显式 `MDF_HOME` 优先。CI job 应设置 `MDF_HOME`。

## 布局

```text
<root>/current -> versions/<revision>/
<root>/versions/<revision>/
<root>/.lock
<root>/logs/
```

- `<revision>` 是完整 commit hash。
- 每次启动解析一次 `current`，之后固定该版本目录。
- 升级或回滚只原子替换 `current`。
- 已启动进程继续使用原目录。

## 命令

这些命令由 `mdf_launcher.py` 处理，不进入 `mdf.py`：

| 命令 | 作用 |
| --- | --- |
| `mdf root` | stdout 一行：本次版本目录绝对路径 |
| `mdf upgrade [--source URL] [--dry-run] [--expected-commit SHA] [--repo PATH]` | 预览或切换到新修订 |
| `mdf restore [--revision SHA]` | 列出已安装修订，或切回其中一版 |
| `install-payload` | 由 `mdf-deploy.sh` 写入一个修订 |

`detach` 与 `contract-switch` 仍由固定版本里的 `mdf.py` 执行。

`--repo` 省略时，当前目录属于带 `.mdf/manifest.yaml` 的 Git 仓库才补齐根 `.gitignore`。
不是这种仓库则跳过。显式 `--repo` 必须是该 Git 根目录，否则升级失败。预览不写 `.gitignore`。

## 引导壳

安装写入用户级 Skill。`SKILL.md` 来自 `assets/host/SKILL.md`。
`scripts/` 是激活版本的 `mdf_launcher.py` 与 `mdf_home.py` 副本，每次激活时原子覆盖。

| 目录 | 宿主 |
| --- | --- |
| `~/.agents/skills/mdf` | Cursor、Codex |
| `~/.claude/skills/mdf` | Claude Code |
| `~/.kiro/skills/mdf` | Kiro |
| `~/.openclaw/skills/mdf` | OpenClaw |

不另写入 `~/.codex/skills` 或 `~/.cursor/skills`。
这两个宿主已经读取 `~/.agents/skills`，再写一份会显示两个同名 Skill。

引导入口不依赖 `~/.local/bin/mdf`。
该链接只在不存在时创建，供人和 CI 直接调用。

## 凭证

兼容修订不改 clear commit 的通过含义。
新的运行日志记录 `tool_revision` 与 `mdf_root`。

- 只有 `schema_version` 变化，或 `.mdf/`、`AGENTS.md` 等业务规则变化，才使对应凭证失效。
- code-review 的 `rules_sha256` 使用协议版本号，不使用协议全文。
- 本机契约低于业务仓声明时，stderr 输出一行：`更新命令：mdf upgrade`。
