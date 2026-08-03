# Mars Development Flow（MDF）

MDF 是一套本地优先的 Agent 文档工作流。它使用版本化文件管理当前事实、工作
意图、重要决策、可执行证据和 Agent 控制面。

## 使用

MDF 只发布一个 Skill。安装后显式调用 `$mdf <command>`：

| 命令 | 用途 |
| --- | --- |
| `$mdf init` | 初始化或更新仓库的 MDF 文档系统 |
| `$mdf start` | 按 Gitflow 创建并推送交付分支 |
| `$mdf review-doc` | 新建或修订单个 active Requirement / Bug |
| `$mdf finish` | 按 Gitflow 分支完成审计与收口 |
| `$mdf audit` | 执行 change audit 或 release audit |
| `$mdf archive` | 归档 closed Requirement 与 Bug |
| `$mdf grill <议题>` | 逐题压力测试计划、决策或想法 |

裸 `$mdf` 只显示帮助。所有工作流都必须显式调用，入口可写入但绝不自动 commit；
用户须复查并提交，下一次调用从 clean worktree 开始。

MDF 仅实现当前契约：不识别、维护或兼容历史 Skill、目录或调用形式。协议、工具与
schema 版本均为数字 `2`。

## 信息分层

| 类型 | 载体 |
| --- | --- |
| 当前事实 | `docs/product/`、`docs/system/`、配置、schema、测试 |
| 意图与工作 | Requirement、Bug、unreleased Change |
| 决策 | `docs/adr/` |
| 证据 | 测试、契约、生成物、配置和命令 |
| Agent 控制面 | `AGENTS.md`、`.mdf/manifest.yaml` |

Requirement/Bug 是计划与偏差，完成后不会自动成为当前事实。当前事实必须可由证据
验证，且不得混写未来计划。

具体工作流、对象约束和仓库契约随唯一 Skill 一同安装，位于其内部的
`workflows/`、`references/`、`assets/` 与 `scripts/`。

## 安装

请从 MDF 仓库获取完整技能集。克隆后用根目录 `link_skills.sh` 安装：

```bash
./link_skills.sh --project /absolute/path/to/target-repository
./link_skills.sh codex --global
```

每次安装或升级都会先卸载目标 Agent skills 目录中的旧 `mdf-*` Skill 和 `mdf`，
再安装当前 `mdf`；不会修改目标仓库的 `.mdf/` 或 `docs/` 产出物。

## 测试

MDF 测试只依赖 Python 标准库、Git 和 pytest：

```bash
python -m pip install -r tests/requirements-test.txt
python -m pytest
```

测试范围和说明见 [tests/README.md](./tests/README.md)。
