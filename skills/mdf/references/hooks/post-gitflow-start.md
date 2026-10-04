# post-gitflow-start

## 配置

```yaml
hooks:
  post-gitflow-start:
    type: command
    path: scripts/post-start.sh
```

- hook 可省略；每项只含 `type` 与 `path`。
- `type`：`command` 执行文件；`rule` 由 Agent 读取规则文件并执行。
- `path`：repo root 相对路径，必须指向新 worktree 内的文件；不得为绝对路径或含 `..`。
- command 文件须有执行权限与 shebang；不追加位置参数。
- 不提供独立 intent。

## 执行契约

- start 成功创建所有 worktree、写入并提交交付材料之后调用一次。
- cwd 为新的 owner worktree；从新 worktree 解析 path，不在 qa/dev 执行。
- command 由 Core 执行；rule 由 start 的 Agent 切到 owner 后读取并执行。
- 上下文含新老 worktree 绝对路径；旧地址是发起 start 的 `--repo`。
  - command 使用 `MDF_NEW_WORKTREE` 与 `MDF_OLD_WORKTREE` 环境变量。
  - rule 的 Agent 从成功 JSON 的 `hook` 读取同名含义的
    `new_worktree`、`old_worktree` 和 `cwd`。
- 执行前输出 hook 名、path、cwd；执行后输出结果，失败时说明原因。
  - command 说明及完整 stdout/stderr 输出到 CLI stderr，并进入 CLI 运行日志。
  - rule 由 Agent 输出前后说明，并按通用运行日志契约记录执行证据。
- 失败仅汇报：start 仍成功，保留 worktree、分支和提交，不回滚，不自动重试。
- start 本身失败时不执行 hook。
