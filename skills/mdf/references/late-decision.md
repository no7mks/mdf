# Late-decision 与按需发布

本页定义 master 起点的 feature 与 on-demand-release（ODR）。其余 feature 保持 develop 起点。
ODR 是独立发布 kind，除本页规定的起点、范围与等待 checkpoint 外，执行 release 的全部工作流。

## 决策树

本页按调用事件核对前置条件；仅返回调用方，不再次调用 start、pr 或 close-out。

```text
┌────────────────────────┐
│ 1 Resolve event        │
└───────────┬────────────┘
            │
            ├──── unknown ────→ [停止并报告]
            │
            ▼ known
┌────────────────────────┐
│ 2 Configure start      │
└───────────┬────────────┘
            │
            ├──── missing input ────→ [澄清或报告阻塞]
            │
            ▼ configured / not start
┌────────────────────────┐
│ 3 Resolve target       │
└───────────┬────────────┘
            │
            ├──── pending ────→ [澄清或报告阻塞]
            ├──── invalid ────→ [保留现场并停止]
            │
            ▼ valid / not required
┌────────────────────────┐
│ 4 Check inclusion      │
└───────────┬────────────┘
            │
            ├──── pending ────→ [等待 feature 侧交付]
            ├──── invalid ────→ [保留现场并停止]
            │
            ▼ ready / not required
┌────────────────────────┐
│ 5 Return               │
└───────────┬────────────┘
            │
            ├──── evidence missing ────→ [停止并报告]
            └──── complete ────────────→ [返回调用方当前步骤]
```

## 工作流（唯一执行契约）

本表只执行当前事件所需的检查；不重跑调用方已完成的阶段。

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Resolve event | 约束 | 核调用事件与交付身份 | 参数或 delivery.json | 2 | 停止并报告 |
| 2 | Configure start | 约束 | 仅 start 应用启动条款；其余跳过 | 启动输入或不适用记录 | 3 | 按入口策略澄清或阻塞 |
| 3 | Resolve target | 约束 | 仅 feature 集成前按目标条款执行 | 目标与依赖或不适用记录 | 4 | 未决按下文处理；无效停止 |
| 4 | Check inclusion | 脚本 | 仅 ODR 恢复、联调、审查、验证、发布前运行 checkpoint | ready 与材料或不适用记录 | 5 | pending 等待；无效停止 |
| 5 | Return | 约束 | 返回原步骤；ODR start 在 hook 与检查后等待 | 检查结论与恢复位置 | 返回调用方 | 缺证据停止 |

## 术语与数据结构

### 事件与调用边界

本节确定每次加载本页实际执行的检查。

- start 事件允许尚无 delivery.json；步骤 2 只准备输入，由 start 创建分支与材料。
- feature 的 design、code-review、verify、fact 不要求具体 target；步骤 3、4 不适用。
- feature 的 catch-up、未合并 pr、local close-out 在集成前执行步骤 3。
  - 已合并 PR 的 close-out 只核对原 PR 与恢复记录；不重新选择目标，也不要求目标 ODR 尚在途。
- ODR start 不执行步骤 4；next / deliver 恢复及后续阶段在 owner 执行步骤 4。
  - deliver 先核 until；被截止时直接返回，不勾 checkpoint 或推进后续阶段。
  - 已开始发布的恢复遵循固定源提交和恢复记录，不重建已归档材料或重选纳入范围。

### Feature 启动与目标

本节定义 start 的输入与默认值。

- `$mdf start --from-master` 从本地 master 创建 feature；支持 `--manual`。
- 可传 `--target develop`、`--target on-demand-release` 或具体 `--target on-demand-release/<version>`。
- 显式目标视为已确认，不在收口前重复询问；仅提供路径时仍须补齐具体 ODR 分支。
- 未传目标时询问 develop、on-demand-release 或暂不决定；未决定记录为 null。
- ready PRP 从 master 读取；planning land 已将规划材料带到 master，再同步 develop。
- 代码依赖与材料可见性分开核对；未发布依赖不能仅靠选择 master 起点解决。
- 不带 `--from-master` 的 feature 保持目标 develop，不增加目标询问。

### Catch-up 前确定目标

local close-out 与 PR mode 的 pr 均须在 catch-up 目标前应用本节；独立 catch-up 也不能绕过。

- 读取 `delivery.json` 的 `base_branch` 与 `target`；已确认的具体目标直接复用。
- 尚未确定时询问；deliver 的 yolo 使用入口已确认的选择或授权的自动裁定，不在中途询问。
- 仅在补齐或改变目标时，在 owner clean 下运行 `delivery target --repo <owner> --target <具体目标>`。
  - 退出 0 后回读 target 并提交 delivery.json；失败保留现场，未提交不得进入集成。
  - 已有相同具体 target 直接复用，不重复调用 setter；PR 创建后只核原目标，不触发 target_locked。
- 核对目标 worktree、实际 Git 历史、PRP 依赖和发布范围，再按原流程 catch-up、补审补验。

- feature → develop：catch-up develop 后合入 develop；不自动创建 release。
- feature → ODR：目标 ODR 必须已 start，且本 feature 在其纳入清单内。
  - catch-up 当前 ODR，验证与已纳入 feature 的组合；不能只验证 master 上的单独功能。
  - local close-out no-ff 合入具体 ODR；PR mode 的 PR 以具体 ODR 为 base。
  - PR mode 在首次 feature PR 前确保目标 ODR 分支已非 force push 到 origin；不得隐式创建 ODR。
  - feature 合入后为 implemented，按自身流程清理；不在此打 tag 或宣称发布完成。
- 已包含 develop 尚未进入 master 的历史，禁止整条 feature 转入 ODR；不 rebase 或自动 cherry-pick。
  - 如果相关历史后来全部进入 master，可重新核对；不是永久按“曾 merge develop”禁止。
  - Git 历史检查不替代代码与业务依赖检查。
- PR 创建后锁定具体目标；恢复复用原 source、target 与 PR，不自动改投。
- 首轮 code-review 与 fact 仍以固定起点确定范围，不因目标选择改写起点或重做已完成阶段。

### ODR 启动与等待

使用 `start --kind on-demand-release --version <semver> --feature feature/<slug>`；多个 feature 重复传 `--feature`。

- 从 master 创建 `on-demand-release/<version>` 与独立 worktree；版本与 release/hotfix 共用 tag 空间。
- start 确认版本、纳入清单、release 工作线和 roster；不实施新 PRP，不在 ODR 里代替 feature 开发。
- objectives 在 start 后写入未勾选的「等待选定 feature 合入」checkpoint。
- start 完成 hook 与 Post-start check 后停下，暂不执行联调、开发或发布验证。
- feature 侧分别发起交付；ODR 不直接拉入未完成收口的 feature。
- next / deliver 恢复 ODR 时先运行 `delivery checkpoint --repo <owner>`。
  - 退出非 0 则保留现场并报告；退出 0 仍须核对 ready，不能仅凭退出码推进。
  - pending 非空则报告清单并停在 checkpoint，不轮询、不越过，也不因 yolo 自动收走 feature。
  - ready 后核对 child Change 与验收材料，勾选该项并提交，再进入 release 后续流程。
  - 以实际 no-ff 合入历史与 Change 为准；feature 的 Change 必须已存在于 merge 的源提交；事后复制材料或手动勾选不能通过。
- 发布范围只含选定 feature；缺失或混入未选定 Change 均停止。

### 发布与恢复

ODR 复用 release 的审查、验证、材料归档、SemVer、tag、发布及恢复要求。
首次发布必须在 owner 核对 checkpoint；`--source` 不能跳过，已有发布记录才可在其他 checkout 恢复。

- branch 验证执行 release suite；首轮审查基线为上一正式发布版本。
- local mode：ODR no-ff 合入 master，创建 tag，按现有发布规则原子 push master 与 tag。
- PR mode：ODR → master 经 PR；实际 merged 后 close-out 发布固定 merge commit。
- 两种模式最终均须 master → develop backmerge；未完成不能报告发布收口完成。
  - local 只回合本地 develop；PR mode 按现有规则完成远端与本地 develop 回合。
- 发布后列出需要包含本次变更的在途 release，由用户确定同步范围，分别补审补验。
- 目标主线前进、冲突、版本竞争与中断沿用 release 的保护规则，不覆盖已有 tag 或已发布材料。
