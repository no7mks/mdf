# Finish

完整读取 `intents/common.md`、`intents/audit.md`、
`references/repository-contract.md` 与 `references/object-contract.md`。

## 决策树

```text
doctor 与 Gitflow 分支有效？
├─ 否 → 停止
└─ 是 → 计算交付范围与当前事实
   └─ 当前 Gitflow 分支类型？
      ├─ feature/bugfix → Change + 范围 audit
      ├─ release → child Change + 全量 audit → release closeout
      └─ hotfix → 结果 JSON + 范围 audit → hotfix closeout

审计或收口完成后
└─ 有写入或 audit 未确认？
   ├─ 是 → 用户复核、commit 后重调
   └─ 否 → finish-gitflow
```

## 工作流（唯一执行契约）

## 交付前检查

1. **脚本**；运行 `doctor` 与 `branch`；证据：manifest `ready`、非 detached、Gitflow
   分支为 `feature/*`、`bugfix/*`、`release/<semver>` 或 `hotfix/<semver>`；
   通过 → 2；失败 → 停止。
2. **约束**；写入前计算交付范围：feature/bugfix 为 `develop...HEAD`，hotfix 为
   `master...HEAD`，release 要求本地 develop；检查范围内代码、配置、schema、测试、
   当前事实、Proposal、Bug、Change，并识别应更新的当前事实文档；证据：精确实现与文档
   路径；通过 → 3；失败 → 停止。这是交付前检查，不是 audit。
3. **约束**；feature/bugfix 迁入既有材料时，要求用户提供来源目录并确认来源、目标
   `changes/unreleased/<slug>` 与链接重写；证据：确认与合法源；通过 → 4；失败 → 无
   材料时创建最小 Change 目录，否则停止。源 slug 须等于分支 slug 且不得含符号链接；
   目标冲突、来源含有目标或非 canonical `CHANGE.md` 时停止；只可用 `move-change`。补齐必要当前事实和 child
   Change；对象保持 ready，不建版本目录或 closeout 根文件。
4. **约束**；内部委托 `audit`：release 执行`全量审阅`，其他分支仅审阅步骤 2 的精确范围；
   证据：零 finding、用户当场确认 warning 和语义摘要；通过 → feature/bugfix 到 9，
   release/hotfix 到 5；失败 → 可修复文档但停止，要求用户复核、commit 后重调 finish。
5. **约束**；release 读取并移动全部 unreleased child Change；hotfix 必须没有 child
   Change 且提供实际结果 JSON；两者均提供规范 `--release-date`，仅用户要求预览时加
   `--dry-run`；证据：版本收口输入；通过 → release 到 7，hotfix 到 6；失败 → 停止。
   Core 仅记录已验证的确定性审计，语义审阅使用本次已确认 audit。
6. **约束**；验证 hotfix `--hotfix-change-json` 只含 body、outcome、ADR、
   `release_notes`、`breaking`、`evidence`；body 非空，
   三类 evidence 字符串列表合计至少一条，release notes 至少一项非空；证据：有效 JSON；
   通过 → 7；失败 → 未知字段、空字符串或缺字段时停止。Core 注入 `change_kind` 与
   `source_branch`。
7. **约束**；以 `--closures-json` 覆盖每个 child Change outcome，并可补录未写 child
   Change 的对象；对每个 active 且 `found_in: unreleased` 的 Bug 分类：fixed 经验证后关闭并写
   `fixed_in`，rejected 使用既有 `reject-reason`，deferred 保持 open；critical 仅 fixed；
   major deferred/wont-fix 要用户接受、理由和 follow-up；duplicate 不进 outcome；
   canonical 与 duplicate 一并归档；证据：完整 closures；通过 → 8；失败 → 停止。
8. **脚本**；调用 `release-closeout`；版本根 Change 聚合 child outcomes/evidence，
   evidence 按首次出现顺序去重并追加 manifest 验证命令；apply 在目标仓库执行命令且必须
   保持 clean 后写入，preview 不执行命令；证据：命令结果和 clean；通过 → 9；
   失败 → 保留现场供用户检查。
9. **约束**；本次写入当前事实或 Change 时展示结果、验证并停止，要求用户复核、commit
   后重调；否则调用 `finish-gitflow --repo "$REPO_ROOT"`；证据：已提交的复查结果；
   通过 → 10；失败 → 停止。
10. **脚本**；CLI fetch 后要求源分支及参与的 master/develop 与 upstream 完全一致；
    feature/bugfix no-ff 合并到 develop；release/hotfix no-ff 合并到 master 后 no-ff 合并
    master 到 develop，并创建注释 `v<semver>` tag，原子 push、删远端及本地源分支；
    证据：合并、tag 和推送结果；通过 → 结束；失败 → 冲突时 CLI abort 并恢复 merge 前状态，
    不推送/删分支；询问用户如何继续，并建议由 MDF 分析解决；写入仍需复核、commit 后重调。
