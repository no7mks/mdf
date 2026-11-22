---
name: mdf-deploy
description: >-
  把当前 MDF 源仓库的 HEAD 安装到本机版本目录。只在 MDF 源仓库中使用。
---

# MDF Deploy

只在本 MDF 源仓库中使用。它安装 `skills/mdf`，不把本体写入业务仓。

## 定位范围

1. 由本文件路径向上三级确定仓库根目录，命名为 `MDF_REPO_ROOT`。
2. 确认存在 `mdf-deploy.sh` 和 `skills/mdf/SKILL.md`。缺失时停止。
3. 确认源仓库工作区干净。不干净时停止。

此流程不接受目标业务仓路径。绝不删除任何仓库的 `.mdf/` 或 `docs/`。

## 命令

安装当前 `HEAD`。省略 `--home` 时由安装脚本选择安装根：

```bash
sh "$MDF_REPO_ROOT/mdf-deploy.sh" install
sh "$MDF_REPO_ROOT/mdf-deploy.sh" install --home /opt/mdf
```

- 修订目录是 `<安装根>/versions/<commit>/`。
- `current` 指向该目录。自检失败时不会留下新的 `current`。
- 业务仓里的旧副本由 `mdf detach` 移除，不由本脚本删除。
