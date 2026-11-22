# 项目入口

MDF 本体是主 worktree 的 `.mdf/cache/mdf-core/<commit>`，只留这一份。该目录是 Skill 树。
薄入口缺这个 commit 时会自动拉取并安装。

| 位置 | 内容 |
| --- | --- |
| `.mdf/cache/mdf-core/<commit>` | 这一修订的本体 |
| `.mdf/cache/mdf-core/.lock` | 安装时的文件锁 |
| `.mdf/cache/mdf-core/.staging-*` | 安装过程中的临时目录，成功后删除 |

`mdf root` 的 stdout 只有一行：该版本目录的绝对路径。launcher 不在 `.mdf/cache/mdf-core/<commit>` 下时返回 `mdf_core_invalid`。

## 命令

这些命令由 `mdf_launcher.py` 处理，不进入 `mdf.py`：

| 命令 | 作用 |
| --- | --- |
| `mdf root` | stdout 一行：版本目录的绝对路径 |
| `mdf upgrade [--source URL] [--dry-run] [--expected-commit SHA] [--repo PATH]` | 预览或安装这一修订 |
| `install-payload` | 由 upgrade 或薄入口把归档写入版本目录 |
| `complete-upgrade --repo PATH --payload PATH --revision SHA --source URL` | 接管本轮已确认并替换的仓内副本 |

`detach` 与 `contract-switch` 仍由该版本目录里的 `mdf.py` 执行。

`--repo` 省略时，当前目录必须属于主 worktree，目标就是该主 worktree。
显式 `--repo` 必须是主 worktree 根；不是 Git 仓库的普通目录也可以。
linked worktree 与子目录都会失败。预览不写文件。

## 替换

1. 解析项目并检查 `.gitignore` 与 cache 路径不是 symbolic link。
2. 取上游 `HEAD`。与 `--expected-commit` 不符则停止，已有版本目录不动。
3. 自检通过后，把版本目录放到 `.mdf/cache/mdf-core/<commit>`。
4. 再发布项目主 worktree 的 `.agents/skills/mdf`。入口里的 `mdf_entry.py` 写明该 commit 和来源。
5. 最后删除其他版本目录。发布失败时保留已就绪的本体，重试同一修订时复用该目录。
6. 自检失败时删除 staging。旧版本目录和项目引导都不变。

## 引导路径

唯一安装路径是项目主 worktree 的 `.agents/skills/mdf`。它包含 `SKILL.md`、
`agents/openai.yaml` 和渲染后的 `mdf_entry.py`，并由仓库根 `.gitignore` 排除。
从 linked worktree 调用时，可运行主 worktree 的 `mdf_entry.py`。入口从自身路径定位项目。

## 已跟踪副本的升级交接

旧版 upgrade 替换并提交仓内副本后，在同一轮重读新版 Skill 时完成交接。
接管命令使用该轮确认的修订和来源，校验待清理的副本，再安装 Core 和项目引导。
成功后暂存旧副本的删除，补齐仓库根 `.gitignore`，返回新入口路径供本轮验证。
失败时还原旧副本、对应 Git index 条目及原 `.gitignore`。
