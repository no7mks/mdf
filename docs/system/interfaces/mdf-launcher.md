# 项目入口

MDF 本体是 `.mdf/cache/mdf-core/<commit>` 下的 Skill 树。每个安装目录只保留当前修订。
upgrade 把本体装到目标 worktree。薄入口缺指定修订时会自动补装。

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
| `check-payload` | 供薄入口检查本体文件，完成自检后输出修订号 |
| `install-payload` | 由 upgrade 或薄入口把本体写入版本目录 |
| `complete-upgrade --repo PATH --payload PATH --revision SHA --source URL` | 接管本轮已确认并替换的仓内副本 |

`detach` 与 `contract-switch` 仍由该版本目录里的 `mdf.py` 执行。

`--repo` 省略时，目标是当前目录所属的 Git worktree 根。
显式 `--repo` 接受任一 Git worktree 根或 Git 仓库外的普通目录。传入 worktree 子目录会失败。
预览不写文件。

## 替换

1. 解析项目并检查 `.gitignore` 与 cache 路径不是 symbolic link。
2. 取上游 `HEAD`。与 `--expected-commit` 不符则停止，已有版本目录不动。
3. 自检通过后，把版本目录放到 `.mdf/cache/mdf-core/<commit>`。
4. 再发布目标 worktree 的 `.agents/skills/mdf`。入口里的 `mdf_entry.py` 写明该 commit 和来源。
5. 最后删除目标 cache 中的其他版本目录。发布失败时保留已就绪的本体，重试同一修订时复用该目录。
6. 自检失败时删除 staging。旧版本目录和项目引导都不变。

## 引导路径

upgrade 在目标 worktree 生成或更新 `.agents/skills/mdf`，由项目提交入口和根 `.gitignore` 的改动。
首次安装生成 `SKILL.md`、`agents/openai.yaml` 和渲染后的 `mdf_entry.py`。普通 upgrade 保持 Git index 不变。
更新已跟踪的薄入口时，覆盖会影响本地修改或额外文件则返回 `entry_dirty`。
`SKILL.md` 运行同目录的 `mdf_entry.py`。脚本从自身路径定位 worktree。
从 linked worktree 调用时，可运行主 worktree 的 `mdf_entry.py`，也可运行当前 worktree 已跟踪的薄入口。
在 linked worktree 升级后，运行该 worktree 的薄入口验证。合入入口改动后，由各 worktree 的薄入口按需补装。

当前 worktree 缺少固定的 `REVISION` 时，已跟踪的薄入口在当前 worktree 生成独立的版本目录，保留薄入口、`.gitignore` 和 Git index。

- linked worktree 先检查主 worktree 的 cache。版本目录名和 `references/.version` 都与 `REVISION` 一致时，薄入口持主 cache 的锁复制本体，再对副本自检。
- 主 cache 没有可用的同版副本时，薄入口从 `SOURCE` 拉取固定的 `REVISION`。
- 共享薄入口所用的 `SOURCE` 须能从其他机器访问。以本机路径安装时，入口会记录该绝对路径。

项目的 `.gitignore` 排除 `.mdf/cache/`、`.mdf/logs/`、`.mdf/reports/` 和 `.mdf/tmp/`。init 和 upgrade 移除 `/.agents/skills/mdf/` 规则。

## 已跟踪副本的升级交接

旧版 upgrade 替换并提交仓内副本后，在同一轮重读新版 Skill 时完成交接。
接管命令使用该轮确认的修订和来源，校验待清理的副本，再安装 Core 和项目引导。
成功后暂存旧副本的删除，更新仓库根 `.gitignore`，返回新入口路径供本轮验证。将新入口和 `.gitignore` 随删除项提交。
失败时还原旧副本、对应 Git index 条目及原 `.gitignore`。
