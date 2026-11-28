# Reconcile

为外部流程的发布补齐记录，或接管无账本发布分支。保留原 workflow 的发布顺序和验收门槛。

树形：not-tree。

## 调用

```text
$mdf reconcile [--version <semver>] [--tag <tag>] [--commit <sha>]
  [--support <major.minor>] [--record-only] [--yolo]
```

- 不接管未 start 的 feature/bugfix。完整 MDF 账本回到 next/deliver/consolidate。
- delivery.json 或 objectives.md 残缺、损坏时停止，不按无账本处理。
- 不创建 delivery.json、objectives.md 或 verification-report.json。
- `--record-only` 只整理记录；没有验收证据时不推进 PRP/Bug 状态，不声称发布完成。
- `--yolo` 省略发布接管确认，不省略证据核验、对象门槛或增量验收。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Inspect | 脚本 | 运行 reconcile inspect，识别发布线与历史区间 | 固定 commit、版本列表 | 2 | 保留现场并停止 |
| 2 | Prepare | 脚本 | 运行 reconcile prepare，进入返回的 worktree | 本地操作记录 | 3 | 修复占用或同步问题 |
| 3 | Reconcile | 约束 | 逐版核实快照或 Git/PR 成果，并准备记录说明 | 原始来源与区间对账 | 4 | 来源不足则停止 |
| 4 | Fact | 约束 | 对齐当前工作区的事实文档并审阅 | 当前 commit/tree 的 fact 结论 | 5 | fact update 后复审 |
| 5 | Apply | 脚本 | reconcile apply 写入并提交该版本记录 | 版本根与 child Change | 6 | 保留现场并停止 |
| 6 | Decide | 约束 | record-only 结束；其余确认是否接管发布 | 用户确认或 yolo | 7 | 交回外部流程 |
| 7 | Finish | 脚本 | 核验证据，reconcile finish 接入原发布链 | 外部 evidence 与真实 Git/平台结果 | 结束 | 补检或等待平台后续办 |

## 两条路径

### 无账本发布分支

- release/* 聚合 child Change；hotfix/* 只写版本根 Change。
- github-flow hotfix 必须属于已发布的 support/<major.minor>；从 trunk 的后续开发历史切出的 hotfix 停止接管。
- 记录整理前核对远端同名分支；远端领先时先同步并完成增量验收。
- 追加实现后重做对账与 fact，再刷新 apply；进入 finish 前补齐与当前候选一致的外部 evidence。

| 发布类型 | 完成记录后的顺序 |
| --- | --- |
| github-flow release | publish 固定候选 → merge/pr → close-out |
| Gitflow release/hotfix | merge/pr → publish 实际 merge commit → close-out 与 develop backmerge |
| github-flow support hotfix | merge → publish → PR mode 的 sync-changelog → close-out |

### 历史发布补账

- 从目标线可达的稳定 SemVer tag 扫描缺账版本；显式 version/tag/commit 可指定历史来源。
- 版本内容取 release_commit 的快照；没有 Change 时按固定区间核查 Git diff 和 PR/MR。
- 快照与当前 unreleased 一致时归档并移除；仅有可分离的 notes/outcomes 追加时留下净增量。
- 正文、归属或证据交织时停止，不留含混半归档记录；连续版本逐版处理。
- 不回滚当前 PRP/Bug，也不把当前事实文档回写成历史实现。
- support 的 commit 按 support 历史核验；向 trunk 导入只写本版记录与 CHANGELOG，不改其 latest_release 或 Bug 真源。

| workflow × mode | 工作区与合入 |
| --- | --- |
| github-flow × pr | pm/reconcile-* 临时 worktree，经 PR 与 CI 后清理 |
| github-flow × local | 临时文档工作区，本地合入 trunk |
| gitflow × pr | pm/reconcile-* 经 PR 合入 trunk，再本地回合 develop |
| gitflow × local | planning worktree，planning land 合入并同步 develop |

pm/reconcile-* 只接受约定文档路径，且排除实际 source/test/extra_inputs/固定输入。
manifest 仅可修改 latest_release。CLI 与 audit-push 均检查每个 commit、rename 两端及 merge 内容。

## 记录与 evidence

Core 使用 `mdf.py reconcile inspect|prepare|apply|finish --repo <path>`。
inspect/prepare 接受 version/tag/commit/support；apply 需要 version、release-date、record-file。
finish 接受 record-only、yolo、evidence-file；清理中断后可用 source 指定原分支续办。

1. 按 [发布对账](consolidate.md) 核实每项成果；不以平台标题猜测内容。
2. fact audit 的右端始终是当前工作区；用上一发布 commit 作 against，首版无基线时审阅 full。
3. 对需要推进状态的对象，先完成 [consolidate](consolidate.md) 与 [bug close](bug-close.md) 的原转换条件。
   缺证据时保持状态；已演进的当前对象有归属冲突时停止澄清。
   条件满足且归属无冲突后，由 Agent 更新并提交对应 PRP/Bug；不得以当前验收代替历史验收。
4. 外部 evidence 必须包含候选 commit/tree、检查 scope、通过结论和可追溯 artifact。
   Agent 读取 artifact 核实结论；链接存在不等于检查通过。
5. 发布前覆盖 lint/build/quick、release 或 smoke、code-review、fact。报告缺项或候选变化时补验。

### JSON 输入

record-file 的字段如下。历史版本的 commit 是固定 release_commit，fact 则绑定当前工作区的 HEAD。

| 字段 | 含义 |
| --- | --- |
| commit | inspect 给出的完整发布或候选 SHA |
| fact | 当前工作区的 evidence 对象，scope 至少含 fact |
| change_kind、source_branch | 无历史版本根时，可指定已核实的历史类型与原分支，不覆盖快照身份 |
| changes | 无历史 Change 时必填；每项含 slug、commits、release_notes，可选 breaking 与 Bug outcomes |
| excluded_commits、exclusions | 不生成 Change 的区间 commits，以及逐 commit 的核对理由 mapping |
| trunk_fixes | support hotfix 的原 Trunk-First 处置记录 |

changes 的 commits 与 excluded_commits 必须完整且不重复覆盖固定区间。
release_notes 沿用 Keep a Changelog 类别，SemVer 按原规则校验。

evidence-file 与 fact 使用同一结构：

```json
{
  "commit": "<完整候选 SHA>",
  "tree": "<该 commit 的 tree SHA>",
  "checks": [{
    "scope": ["lint", "build", "quick", "release", "code-review", "fact"],
    "passed": true,
    "artifacts": ["https://ci.example.test/runs/123"]
  }]
}
```

- hotfix 使用 smoke；post_hoc 文档合入需要 lint 与 fact。
- artifacts 接受可追溯 HTTP(S) 链接或该候选已跟踪的仓内文件；Agent 读取并核实内容。
- Core 校验精确 commit/tree、scope、通过状态及来源格式。缺项或候选变化时拒绝发布。

## 续办

- apply 会提交记录。后续 evidence 必须绑定提交后的候选；不把旧 fact 结论冒充成新候选的完整验收。
- finish 返回 integration_required 时，按返回 plan 执行增量 CR、smart verify、FA，必要时刷新记录。
  发布后的 github-flow release 保留原 release_head 与 tag，不移动 tag。
- 返回 pr-watch 时沿用 [PR](pr.md) 的 CI/review 等待与修复规则；通过后再次执行 reconcile finish。
- squash 使用原分析及执行入口；不能用 squash 隐藏补账通道中的代码提交。
- final tag 始终使用原 annotated tag 校验；post_hoc 可记录外部 lightweight tag，但不得重写远端 tag。
