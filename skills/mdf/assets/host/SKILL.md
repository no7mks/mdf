---
name: mdf
description: >-
  管理 Git 仓库的版本化文档与交付流程。本文件只负责定位 MDF 本体。
disable-model-invocation: true
---

# Mars Development Flow

本文件是指针，不含 MDF 本体。

1. 在当前读取的 `SKILL.md` 所在目录执行：

   ```bash
   python3 -B ./mdf_entry.py
   ```

2. 退出码非 0：原样报告 stderr 并停止，不模拟 CLI。
3. 退出码为 0：stdout 唯一一行就是 `MDF_ROOT`。
   完整读取 `$MDF_ROOT/SKILL.md`，只按该文件执行。
