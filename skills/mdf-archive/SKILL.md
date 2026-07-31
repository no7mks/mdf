---
name: mdf-archive
description: >-
  仅在用户显式调用时，将 closed Requirement 与 Bug 归档到指定
  MAJOR.MINOR 切片，并重写仓库内引用。
disable-model-invocation: true
---

# MDF Archive

只在用户显式调用 `$mdf-archive` 时执行。不要因对象 closed、目录变大或发布完成而自行触发。

## 前提

1. 按 `mdf-core` 的“入口 Skill 解析 Core”规则验证 V2 Core，解析 `REPO_ROOT`。
2. 用户提供精确 `MAJOR.MINOR` 切片 `RELEASE_EPOCH`；拒绝 patch、预发布、构建元数据和 `unreleased`。
3. 运行 doctor，只有 manifest `ready` 且 worktree clean 时继续：

   ```bash
   python3 "$MDF_CORE_SCRIPT" doctor --repo "$REPO_ROOT"
   ```

## 预览或执行

用户要求预览时才运行：

```bash
python3 "$MDF_CORE_SCRIPT" archive --repo "$REPO_ROOT" \
  --epoch "$RELEASE_EPOCH" --dry-run
```

检查输出只涉及 closed Requirement/Bug 的稳定移动，以及仓库内旧 canonical 路径的引用重写。preview 不构成确认或参数绑定
。

用户显式调用本入口即授权实际归档时，运行：

```bash
python3 "$MDF_CORE_SCRIPT" archive --repo "$REPO_ROOT" \
  --epoch "$RELEASE_EPOCH"
```

Core 直接写入后做 full validation。失败时停止并保留 Git worktree 现场。成功后报告归档对象、切片、重写数量和 full
validation 结果；不自动提交 Git。
