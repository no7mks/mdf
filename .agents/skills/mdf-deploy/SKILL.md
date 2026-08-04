---
name: mdf-deploy
description: >-
  以安装基线比较外部项目与本地的 MDF Skill，并安装或卸载。当需要维护外部项目的
  MDF 时使用。
---

# MDF Deploy

只在本 MDF 源仓库中使用。它维护 `skills/mdf`，不属于对外安装的 Skill。

## 定位范围

1. 由本文件路径向上三级确定仓库根目录，命名为 `MDF_REPO_ROOT`，确认存在
   `mdf-deploy.sh` 和 `skills/mdf/SKILL.md`；缺失时停止。
2. 先取得目标项目的绝对路径并命名为 `TARGET_REPO`。脚本扫描其中已有的受支持
   Skills 目录；未找到时停止。
3. 此流程只处理已找到的 Skills 目录中的 `mdf`。绝不删除目标项目的 `.mdf/`、
   `docs/` 或业务文件。

## 命令

比较本地与目标相对安装基线的改动：

```bash
sh "$MDF_REPO_ROOT/mdf-deploy.sh" diff \
  --target "$TARGET_REPO"
```

每个已安装 `mdf` 的 `references/.version` 记录安装时的完整 commit hash。`diff` 用
该 commit 分别比较本地与目标，因此本地与目标同时改动时仍可判断双方相对基线的变化。
根据结果向用户说明可采纳项，并询问是否采纳、采纳哪些。用户确认后，由 Agent 修改
本地 `skills/mdf`；脚本不提供 `merge` 命令。

安装前确认 MDF 源仓库工作区干净。`install` 仅归档当前 `HEAD`，并写入基线文件：

```bash
sh "$MDF_REPO_ROOT/mdf-deploy.sh" install \
  --target "$TARGET_REPO"
```

目标已有 `mdf` 时先卸载：

```bash
sh "$MDF_REPO_ROOT/mdf-deploy.sh" unistall \
  --target "$TARGET_REPO"
```
