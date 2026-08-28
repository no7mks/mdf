# Start

完整读取 `intents/common.md`。一次只启动一个分支，不自动 commit。

## 决策树

```text
分支类型与标识 → 参数有效？否：询问；是 → start CLI
→ Git/基线可用？否：报告并停止；是 → 创建、推送、设 upstream
```

## 工作流（唯一执行契约）

1. **约束**；一次只要求一个分支的类型和必要标识：feature/bugfix 要 slug，
   release/hotfix 要稳定 SemVer；证据：明确参数；通过 → 2；失败 → 询问。
   不得从自然语言猜测版本。
2. **脚本**；运行 `start --repo "$REPO_ROOT" --kind <kind>`，feature/bugfix 使用
   `--name <slug>`，release/hotfix 使用 `--version <semver>`；CLI 在同一次调用中 fetch，
   检查 `origin`、默认 `master`、来源及 upstream 一致、clean、目标不存在，再从 develop
   创建 feature/bugfix/release 或从 master 创建 hotfix、推送到 origin 并设置 upstream；
   证据：检查、分支、远端与 upstream；通过 → 结束；失败 → 不创建分支并报告 finding；
   基线已推进时先询问用户并建议由 MDF 分析解决。绝不自动 commit。
