---
name: mdf-init-repo
description: >-
  仅在用户显式调用时，初始化既有 Git 仓库的 Mars Docs Flow 文档系统；
  需要逐题澄清时使用 mdf-grill 收敛基线、版本和验证配置。
disable-model-invocation: true
---

# MDF Init Repo

只在用户显式调用 `$mdf-init-repo`
时执行。不要因仓库缺少文档或 MDF 未初始化而自行运行；不要自动 commit。

## 解析依赖与写入方案

1. 按 `mdf-core` 的“入口 Skill 解析 Core”规则验证 Core，并解析同级 `mdf-grill`
   的绝对路径、完整读取其 `SKILL.md`。
2. 解析目标 Git 根为 `REPO_ROOT`，要求 clean worktree，然后运行：

   ```bash
   python3 "$MDF_CORE_SCRIPT" doctor --repo "$REPO_ROOT"
   ```

3. canonical 路径已有内容时，先展示完整写入方案：受影响路径、保留内容、拟补字段、八项基线、最近稳定版本、验证命令和预期 validation。
   只有用户对这份完整写入方案明确确认后，才调用 Core
   init 或写入；不得自动覆盖、移动或删除既有内容。

## 使用 mdf-grill 收敛

通过 `mdf-grill` 一次一题收敛，并先从仓库证据确认可回答的事实：

- 八项基线：glossary、product reference、system
  boundary、architecture、interfaces、data、operations、deviations；每项是已验证的
  `documented:<repo-relative-path>`，或有明确理由的 `not_applicable:<reason>`；
- 最近稳定版本：交叉核对既有材料、稳定版本根 CHANGE 与 CHANGELOG；从未发布才为
  `none`；
- `verification.commands`：在目标仓库运行的非空受信任命令列表。命令的产物必须自行清理或被
  `.gitignore` 忽略。

不把未知或未来计划写成当前事实。在本次调用中，收敛和必要的写入确认完成后才由本入口写事实页、`CONTEXT.md`
与配置。任何配置调整（包括验证命令）都重新显式调用
`$mdf-init-repo`，不要绕过该入口直接改 manifest。

## 初始化、暂停与显式续办

1. 用户要求时可预览 Core 初始化：

   ```bash
   python3 "$MDF_CORE_SCRIPT" init --repo "$REPO_ROOT" \
     --latest-release "<stable-semver|none>" \
     --baseline "<name>=documented:<repo-relative-path>" \
     --baseline "<name>=not_applicable:<reason>" --dry-run
   ```

   preview 只是信息，不替代既有内容写入方案的确认。Core `init`
   不接收验证命令参数。

2. 用户确认后去掉 `--dry-run` 执行相同的 Core
   init。Core 先写 scaffold，manifest 保持 `initializing` 且
   `verification.commands: []`。按确认方案写入 `verification.commands`，并保留
   `AGENTS.md` 的非 MDF 托管块。
3. 明确比较本次调用前后的
   `CONTEXT.md`、`docs/product/**`、`docs/system/**`。只要其中任一文件新增或修改，manifest 必须保持
   `initializing`；展示事实页 diff，停止，不转 ready、不宣称 full
   validation 已完成。要求用户复核并 commit，然后由用户再次显式调用
   `$mdf-init-repo`。
4. 续办调用必须从 clean worktree 开始。先确认本次不再改事实页，运行 full
   validation，并只接受一个 finding：
   `manifest.initializing`。有任何其他 finding 时停止并报告；不得用 ready 掩盖它们。仅此时才把 manifest 改为
   `ready`，再运行：

   ```bash
   python3 "$MDF_CORE_SCRIPT" validate --repo "$REPO_ROOT" --scope full
   ```

5. 若复用的既有事实页在本次完全未改动，且八项基线与非空验证命令已经可验证，可直接执行第 4 步，不需要额外暂停。任一步失败都保留现场并报告
   findings；不自动提交 Git。ready 后用户自行复查并 commit，再开启下一次 MDF 入口。
