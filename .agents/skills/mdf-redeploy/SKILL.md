---
name: mdf-redeploy
description: >-
  审查外部项目中的 MDF 测试改动、提出可回收的源 Skill patch，并在用户确认后
  重新部署当前 skills/mdf。当需要检查或重新部署外部项目的 MDF 时使用。
---

# MDF Redeploy

只在本 MDF 源仓库中使用。它维护 `skills/mdf`，不属于对外安装的 Skill。

## 定位范围

1. 由本文件路径向上三级确定仓库根目录，命名为 `MDF_REPO_ROOT`，确认存在
   `redeploy_mdf.sh`、`link_skills.sh` 和 `skills/mdf/SKILL.md`；缺失时停止。
2. 先取得目标项目的绝对路径并命名为 `TARGET_REPO`。脚本扫描其中已有的受支持
   Skills 目录；未找到时停止。
3. 此流程只处理已找到的 Skills 目录中的 `mdf-*` 与 `mdf`。绝不删除目标项目的
   `.mdf/`、`docs/` 或业务文件。

## 只读审查

运行：

```bash
sh "$MDF_REPO_ROOT/redeploy_mdf.sh" report \
  --target "$TARGET_REPO"
```

然后按需读取目标仓库的 staged、unstaged 和未跟踪改动，以及已安装 `mdf` 的具体
差异。审查源仓库中 `skills/mdf/`、`link_skills.sh` 和部署脚本的相关改动。

将每项发现归为以下之一：

- 目标项目的业务实例或当前事实：留在目标，不能带回源仓库；
- 可复用的工作流、模板或确定性脚本问题：提出最小源仓库 patch 与测试；
- 源仓库特有内容：说明下发到目标后的行为影响；
- 无关或证据不足：明确不处理及原因。

## 结论与部署

先用简短结论列出：要带回源仓库的 patch、只留在目标的改动、将下发的源改动，
以及不处理项。然后要求用户明确确认这个结论。未确认时停止，不 patch、不部署。

确认后，才修改已确认的源文件并运行相关测试。随后运行：

```bash
sh "$MDF_REPO_ROOT/redeploy_mdf.sh" deploy \
  --target "$TARGET_REPO" --yes
```

`--yes` 只表示用户已经确认本次结论；脚本不会再次询问。报告部署结果并验证目标
`mdf` 与当前 `skills/mdf` 内容一致；不要自动 commit。
