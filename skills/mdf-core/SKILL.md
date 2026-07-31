---
name: mdf-core
description: >-
  Mars Docs Flow 的被动共享协议、模板与确定性 CLI。仅在 mdf-* 入口 Skill
  显式委托仓库诊断、初始化、校验、Gitflow 检查、Change 移动、 release closeout
  或归档时加载；绝不直接承接用户业务请求。
disable-model-invocation: true
---

# Mars Docs Flow Core

只作为 `mdf-*` 入口 Skill 的基础设施。不要把直接用户请求当成运行业务流程的授权。

## 建立契约

1. 运行 `python3 scripts/mdf.py info`，要求 `protocol_version`、`tool_version`
   与 `schema_version` 均为数字 `2`。
2. 按操作需要读取：
   - [repository-contract.md](references/repository-contract.md)
   - [object-contract.md](references/object-contract.md)
   - [workflows.md](references/workflows.md)
3. 显式解析全部仓库路径；不要假设当前工作目录就是目标仓库。

## 入口 Skill 解析 Core

入口从自身 `SKILL.md` 的绝对路径解析同级
`../mdf-core`（或使用安装器注册的绝对路径），确认 `SKILL.md` 和 `scripts/mdf.py`
存在后运行：

```bash
python3 "$MDF_CORE_SCRIPT" info
```

协议主版本不是
`2`、Core 缺失或命令失败时停止。不要模拟 Core，也不要让 Core 直接接单。

## 机械操作

```bash
python3 scripts/mdf.py doctor --repo /absolute/repo
python3 scripts/mdf.py validate --repo /absolute/repo --scope targeted
python3 scripts/mdf.py validate --repo /absolute/repo --scope full
python3 scripts/mdf.py init --repo /absolute/repo --latest-release none \
  --baseline glossary=documented:CONTEXT.md ...
python3 scripts/mdf.py move-change --repo /absolute/repo \
  --source /absolute/repo/.scratch/feature-a --branch-slug feature-a
python3 scripts/mdf.py archive --repo /absolute/repo --epoch 1.3
python3 scripts/mdf.py release-closeout --repo /absolute/repo \
  --release-date 2026-07-30 \
  --semantic-attestation-json \
  '{"semantic":"passed","finding_count":0,"summary":"..."}'
```

`--dry-run`
是可选预览：只在用户要求预览时添加。它不产生确认、digest 或后续 apply 绑定。stdout 是机器可读 JSON；
`validate` 出现 finding 时以 stdout JSON 和退出码 `2`
报告，其他执行错误使用 stderr JSON。

## 写入纪律

- `init`、`move-change`、`archive`、`release-closeout`
  在 preview 与 apply 前都要求目标 Git worktree clean。
- Core 直接写入目标仓库；写入或 post-validation 失败时保留现场，交由 Git 历史和用户处理。
- `archive` 与 `release-closeout` apply 后做 full
  validation。不得手工补做半套移动。
- 初始化的 manifest 以 `state: initializing` 和 `verification.commands: []`
  开始。只有入口已将八项基线、事实页和非空验证命令写妥后，才能转为 `ready`
  并通过 full validation。
- 若 init 新增或修改
  `CONTEXT.md`、`docs/product/**`、`docs/system/**`，入口必须保留 initializing，等待用户复核提交后由
  `$mdf-init-repo` 显式续办；续办 preflight 只允许 `manifest.initializing`
  finding。
- `release-closeout` 只接收 `$mdf-finish` 组装的内存参数。它从 ready
  manifest 读取并只在 apply 时执行
  `verification.commands`；命令成功后 worktree 仍须 clean，否则停止。preview 不执行命令。
- `release-closeout` 必须显式提供
  `--release-date`；hotfix 必须提供严格的结果 JSON。Core 生成 hotfix
  identity，并把 child/hotfix
  evidence 与 manifest 验证命令按首次出现顺序聚合到版本根 Change。
- `--semantic-attestation-json`
  在 preview/apply 都必填，必须是 passed、零 finding、非空 `summary`，且禁止
  `waivers`。major Bug 的 deferred / `wont-fix`
  仍需要用户明确接受、理由和follow-up。

CLI 只做确定性工作；调用入口仍负责代码、测试、配置与散文的语义比较。保持本 Skill 被动；业务入口是
`mdf-audit`、 `mdf-init-repo`、`mdf-review-doc`、`mdf-finish`、`mdf-archive`。
