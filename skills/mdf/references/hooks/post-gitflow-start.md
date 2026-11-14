# post-start

## 配置

```yaml
hooks:
  post-start:
    type: command
    path: scripts/post-start.sh
```

- hook 可省略；每项只含 `type` 与 `path`。
- `post-gitflow-start` 是 `post-start` 的 manifest 别名；同一份 manifest 只能配置其中一个。
- `type`：`command` 执行文件；`rule` 由 Agent 读取规则文件并执行。
- `path`：repo root 相对路径，必须指向新 worktree 内的文件；不得为绝对路径或含 `..`。
- command 文件须有执行权限与 shebang；不追加位置参数。
- 不提供独立 intent。

执行步骤见 [workflow](../post-gitflow-start.md)；本页只定义配置与调用接口。
