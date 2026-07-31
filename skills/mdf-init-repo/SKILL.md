---
name: mdf-init-repo
description: >-
  仅在用户显式调用时，初始化既有 Git 仓库的 Mars Docs Flow V2 文档系统；
  需要逐题澄清时使用 mdf-grill 收敛基线、版本和验证配置。
disable-model-invocation: true
---

# MDF Init Repo

只在用户显式调用 `$mdf-init-repo` 时执行。不要因仓库缺少文档或 MDF 未初始化而自行运行；不要自动 commit。

## 解析依赖与迁移方案

1. 按 `mdf-core` 的“入口 Skill 解析 Core”规则验证数字 V2 Core，并解析同级 `mdf-grill` 的绝对路径、完整读取其
   `SKILL.md`。
2. 解析目标 Git 根为 `REPO_ROOT`，要求 clean worktree，然后运行：

   ```bash
   python3 "$MDF_CORE_SCRIPT" doctor --repo "$REPO_ROOT"
   ```

3. 所有既有仓库都按接入 MDF V2 处理。旧 MDF/V1 文件只是可参考的既有材料：不兼容 V1 schema、参数或运行时分支。
4. 既有 canonical 路径的内容与 V2 不兼容时，先展示完整迁移方案：受影响路径、保留内容、原地迁移或补充字段、八项基线、最近稳定版本、验证命令和预
   期 validation。只有用户对这份完整方案明确确认后，才调用 Core init 或原地写入；不得自动覆盖、移动或删除既有内容。

## 使用 mdf-grill 收敛

通过 `mdf-grill` 一次一题收敛，并先从仓库证据确认可回答的事实：

- 八项基线：glossary、product reference、system boundary、architecture、interfaces、data、
  operations、deviations；每项是已验证的 `documented:<repo-relative-path>`，或有明确理由的
  `not_applicable:<reason>`；
- 最近稳定版本：交叉核对既有材料、稳定版本根 CHANGE 与 CHANGELOG；从未发布才为 `none`；
- `verification.commands`：在目标仓库运行的非空受信任命令列表。命令的产物必须自行清理或被 `.gitignore` 忽略。

不把未知或未来计划写成当前事实。在本次调用中，收敛和必要的迁移确认完成后才由本入口写事实页、`CONTEXT.md` 与配置。任何配置调整（包括验证命令）都重新
显式调用 `$mdf-init-repo`，不要绕过该入口直接改 manifest。

## 初始化与验证

1. 用户要求时可预览 Core 初始化：

   ```bash
   python3 "$MDF_CORE_SCRIPT" init --repo "$REPO_ROOT" \
     --latest-release "<stable-semver|none>" \
     --baseline "<name>=documented:<repo-relative-path>" \
     --baseline "<name>=not_applicable:<reason>" --dry-run
   ```

   preview 只是信息，不替代既有内容迁移方案的确认。Core `init` 不接收验证命令参数。
2. 用户确认后去掉 `--dry-run` 执行相同的 Core init。Core 先写 V2 scaffold，manifest 保持
   `initializing` 且 `verification.commands: []`。
3. 按确认方案原地迁移或补充既有 canonical 内容，写入已收敛并验证的事实页、`CONTEXT.md` 和 manifest
   `verification.commands`；保留 `AGENTS.md` 的非 MDF 托管块。
4. 仅当全部基线可验证、验证命令非空时，把 manifest 转为 `ready`，并运行：

   ```bash
   python3 "$MDF_CORE_SCRIPT" validate --repo "$REPO_ROOT" --scope full
   ```

5. 失败时保留现场并报告 findings；不自动提交 Git。成功后用户自行复查并 commit，再开启下一次 MDF 入口。
