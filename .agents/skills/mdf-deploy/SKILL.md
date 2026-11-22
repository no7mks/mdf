---
name: mdf-deploy
description: >-
  把当前 MDF 源仓库的 HEAD 装进目标项目的本体缓存。只在 MDF 源仓库中使用。
---

# MDF Deploy

只在本 MDF 源仓库中使用。它把 `skills/mdf` 装进目标项目的
`.mdf/cache/mdf-core/<commit>`。目标项目的 `.agents/skills/mdf` 引导会记下这个本地源路径。

## 定位范围

1. 由本文件路径向上三级确定仓库根目录，命名为 `MDF_REPO_ROOT`。
2. 确认存在 `skills/mdf/SKILL.md`。缺失时停止。
3. 确认源仓库工作区干净。不干净时停止。
4. 目标项目路径由调用者给出，命名为 `<目标>`。

此流程绝不删除任何仓库的 `.mdf/` 或 `docs/`。

## 命令

安装当前 `HEAD`：

```bash
python3 -B "$MDF_REPO_ROOT/skills/mdf/scripts/mdf_launcher.py" upgrade \
  --source "$MDF_REPO_ROOT" --repo "<目标>" \
  --expected-commit "$(git -C "$MDF_REPO_ROOT" rev-parse HEAD)"
```

- 本体只有目标项目里的一份 `<commit>` 目录。
- 自检失败时旧版本目录和项目引导不变。
- 业务仓里的旧副本由 `mdf.py detach` 移除，不由本流程删除。
