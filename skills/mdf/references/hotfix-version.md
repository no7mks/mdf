# Hotfix 名称与发布版本

本页定义 hotfix 分支名、发布版本及材料目录的对应关系。

## 分支名与 start

Hotfix 从本地 master 创建，分支名接受稳定 SemVer 或 kebab-case slug。

| 形式 | start 参数 | 发布版本 |
| --- | --- | --- |
| `hotfix/1.2.1` | `--kind hotfix --version 1.2.1` | 分支版本 `1.2.1` |
| `hotfix/fix-login`，提前约定 | `--kind hotfix --name fix-login --version 1.2.1` | 固定为 `1.2.1` |
| `hotfix/fix-login`，收口定版 | `--kind hotfix --name fix-login` | 在收口材料准备时固定 |

- 三种形式均须传入 `--objectives-file`；分支基线和独立 worktree 规则沿用 start。
- slug 仅接受小写 ASCII 字母、数字和单个分隔连字符；不接受空段、下划线或嵌套路径。
- 版本仅接受 `major.minor.patch`，无前导零、prerelease 或 build metadata。
- tag 始终为 annotated `v<version>`，不使用 slug 作为 tag。

## 收口定版

本节规定版本确定的时点，避免 Bug、版本材料与 tag 使用不同版本。

1. local close-out 集成 master 后、Bug close 与版本材料生成前，确认当前本地 master 已与远端对齐。
   PR mode 在准备 PR 候选发布材料时定版，不等到 merged 后。
2. 有 origin 时先 fetch master 与 tags；本地 master 有分歧则保留现场并停止，不自动 reset 或 rebase。
3. 在 hotfix owner 执行 `delivery resolve-version --repo <owner>`，读取返回的 `version` 与 `tag`。
4. 提交更新的 `delivery.json`，再使用该版本完成 Bug close、release-closeout 与后续发布。

| 版本来源 | resolve-version 的处理 |
| --- | --- |
| SemVer 分支或已有 `delivery.json.version` | 复用固定版本，不重新计算 |
| slug 未约定版本 | 从 master 历史可达的 `v<稳定 SemVer>` 中按数值取最大值，patch 加 1 |
| master 没有有效 tag | 返回 `missing_release_tag`；请求显式版本后传 `--version <semver>` |

- `v1.2.9`、`v1.2.10` 均可达时生成 `v1.2.11`；忽略其他分支上的 tag 与非稳定版本 tag。
- 不按 tag 创建时间、字典顺序或第一父链距离排序。
- 已固定版本后传入不同 `--version` 返回 `hotfix_version_changed`；重试不得自动改版。
- 如果目标 tag 已被其他发布占用，保留现场并报告冲突，不覆盖 tag 或跳号重试。
- `release-closeout --dry-run` 可预览未固定 slug 的自动版本，不写入。
- 直接执行 `release-closeout` 时复用约定版本；未约定则计算版本，并在成功归档时写入身份。

## 材料与发布

本节区分稳定的交付 slug 与发布版本目录。

| 分支 | start 后材料目录 | 成功收口后材料目录 |
| --- | --- | --- |
| `hotfix/1.2.1` | `changes/unreleased/1.2.1/` | `changes/1.2.1/` |
| `hotfix/fix-login` | `changes/unreleased/fix-login/` | `changes/<version>/` |

- `delivery.json.branch` 与 `slug` 保留原交付身份；slug hotfix 另外保存稳定 SemVer `version`。
- 根 `CHANGE.md.source_branch` 保留真实分支，例如 `hotfix/fix-login`。
- Hotfix 不创建 child Change；自身材料目录不作为待发布 child Change。
- PR 候选归档后，delivery、verify 与 CI review 使用同一版本目录，不重建 unreleased 副本。
- Bug close 的 `--fixed-in` 必须等于已固定版本；未定版时先 resolve-version 并提交。
- local 与 PR mode 的 merge、tag、backmerge 和清理规则沿用 close-out。
- 发布和恢复读取固定源提交中的版本；不得因 master 或 tags 后续前进而重新计算。
- slug 的发布记录按 start_commit 隔离；完成清理并移除保留 worktree 后，可再次 start 同一 slug。
  - 新交付不复用旧 PR 或版本；源分支删除后按最近一次 start 的固定起点恢复。
