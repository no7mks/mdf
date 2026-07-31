---
name: mdf-review-doc
description: >-
  仅在用户显式调用时，依赖 MDF Core 新建或修订单个 Requirement/Bug；
  需要逐题澄清时使用 mdf-grill，并在用户确认后转为 ready。
disable-model-invocation: true
---

# MDF Review Doc

只在用户显式调用 `$mdf-review-doc`
时执行。不要在普通需求讨论、Bug 排查或编码任务中自行接管文档评审；不要自动 commit。

## 开始会话

1. 按 `mdf-core` 的“入口 Skill 解析 Core”规则验证 Core，并解析、完整读取同级
   `mdf-grill` 的 `SKILL.md`。
2. 解析目标 Git 根 `REPO_ROOT`，要求 clean worktree 后运行：

   ```bash
   python3 "$MDF_CORE_SCRIPT" doctor --repo "$REPO_ROOT"
   ```

3. 仅在 manifest 为 `ready` 时继续；否则提示用户显式调用
   `$mdf-init-repo`。一次只评审一个 Requirement 或 Bug。

## 新建或修订

1. 新对象先由用户指定 Requirement/Bug 类型与 slug，收敛后用 Core `make-id`
   创建 draft。
2. 修订既有对象时，用户必须给出 canonical
   ID（`req-`/`bug-`）或 canonical 仓库相对路径；缺失或歧义时委托 `mdf-grill`
   一次只问一个消歧问题。只允许 active（draft/ready）对象；closed 或 archive 对象拒绝修改。
3. 既有 ready 对象在开始评审时立即转为
   `draft`。显式取消、暂不继续或未确认最终内容时保留
   `draft`；用户自行 commit 后可在后续会话继续评审。
4. 对新建与既有 draft 都先委托
   `mdf-grill`。它一次只澄清一个影响成稿的事实或决策；先查仓库证据，再询问用户的取舍。
5. Requirement 必须收敛 Problem、Desired
   Outcome、Scope（In/Out）和可验证 Acceptance
   Criteria。Bug 必须收敛 Observed/Expected
   Behavior、Reproduction、Impact、Regression Evidence Required、`found_in`
   与 active
   severity。仅当决策长期存在或难逆转、缺背景会令人意外且有真实取舍时建议 ADR。

## 成稿确认与 Ready

1. 完整展示 draft、已确认事实和明确排除范围；修订既有对象时同时展示与开始前内容的 diff。
2. 只有用户对这份具体 Requirement/Bug 内容明确确认后，才进行 ready 转换；沉默不是确认。
3. 确认后运行定向验证：

   ```bash
   python3 "$MDF_CORE_SCRIPT" validate --repo "$REPO_ROOT" --scope targeted
   ```

4. 定向验证通过后转为 ready，并报告路径、ID、状态和关联关系。普通对象不在此流程关闭，也不填
   `fulfilled_in`/`fixed_in`；duplicate 仅在用户确认后可写为 closed
   duplicate。其 canonical 可以仍为 ready；duplicate 不进 Change
   outcome，也不能在 canonical 关闭前通过手动 archive 单独移动。
5. 验证失败时保留 draft 和现场，报告 finding，不宣称 ready。用户自行复查并 commit；不自动提交 Git。
