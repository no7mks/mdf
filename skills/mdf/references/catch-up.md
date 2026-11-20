# Catch-up

同步 `origin/<当前工作分支>`，在本步骤内完成同步增量验收。适用于 feature、bugfix、release 等交付。

树形：not-tree。

## 工作流（唯一执行契约）

| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Sync | 脚本 | 执行 catch-up，同步远端同名工作分支 | base、remote、plan | 2 | 解决冲突后续办 1 |
| 2 | Validate | 约束 | 按 plan 执行增量 CR、smart verify、增量 FA | 本轮报告与修复 | 3 | 在本步骤内修复并补检 |
| 3 | Complete | 脚本 | 核对 reviewed-head 与远端，完成同步记录 | 自勾与完成 commit | consolidate | 远端前进回 1 |

## 同步与验收

```bash
python3 "$MDF_ROOT/scripts/mdf.py" catch-up --repo "$REPO_ROOT"
```

- 进入前提交本次改动，保持 clean；先完成必要 squash。
- 远端同名分支存在时 fetch 后合入，线性历史允许 fast-forward，分歧使用 merge。
- 无 origin 或远端同名分支时，以当前已验收内容继续。
- 首轮 base 为同步前的本地 HEAD；未完成的同一轮一直保留 base。
- 上轮完成后再同步，以 completed_head 为新 base。冲突、修复和本轮新增提交都纳入增量。
- 按 plan 的 review、verify、fact 三路执行适用检查，复用 [incremental-integration](incremental-integration.md) 的补检方法。
- 原 lint、code-review、verify、fact 已勾项保持 `[x]`。新增验收属于 catch-up，报告追加，验证写独立报告。
- 采用 `catch-up-verification-report.json` 保存本轮验证结果；保留原 verification-report.json。

```bash
python3 "$MDF_ROOT/scripts/mdf.py" catch-up --repo "$REPO_ROOT" \
  --complete --reviewed-head <完整SHA> --summary "本轮增量审查、验证和事实补检结论"
```

- 验收通过后执行 complete，自勾 catch-up。CLI 核对当前 HEAD 与远端包含关系。
- 阶段提交失败时，可续办本次精确的 objectives 改动；重复完成保持幂等。
- hook 或并发提交引入额外内容时，保留现场，本轮仍未完成；next/route 继续 catch-up，consolidate/merge 不能越过。
- 已勾 checklist 不覆盖未完成的本轮记录；再次验收新增内容后才可继续，不退勾原 CR、verify、FA。
- 远端再次前进时，在本步骤内重新同步与验收，再进入 consolidate。
- catch-up 完成后允许 consolidate 产生已核验的材料提交。publish 继续核对远端同名分支是否有未纳入的提交。
