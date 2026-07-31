# Mars Docs Flow（MDF）

MDF 是一组本地优先的 Agent 文档 Skill。它使用版本化文件管理当前事实、
工作意图、重要决策、可执行证据和 Agent 控制面。

## 技能集

| 组件 | 用途 |
|---|---|
| `mdf-core` | 共享协议、模板与确定性 CLI；不是业务入口 |
| `mdf-init-repo` | 初始化或迁移仓库到 MDF V2 |
| `mdf-review-doc` | 新建或修订单个 active Requirement / Bug |
| `mdf-finish` | 按 Gitflow 分支完成审计与收口 |
| `mdf-audit` | 执行 change audit 或 release audit |
| `mdf-archive` | 归档已关闭工作项并重写链接 |
| `mdf-grill` | 逐题压力测试计划、决策或想法 |

所有组件作为 V2 套件发布。入口仅在用户显式调用时执行；`mdf-core` 是内部
被动组件。完整协议、工作流与约束见
[Mars Docs Flow 文档](./docs/mars-docs-flow.md)。

## 安装

请前往 [MDF 独立仓库](http://10.1.5.65:8929/mars/mdf) 获取并安装完整技能集。
克隆仓库后，可用根目录的 `link_skills.sh` 将所有技能软链到目标项目或用户级
Agent skills 目录：

```bash
./link_skills.sh --project /absolute/path/to/target-repository
./link_skills.sh codex --global
```

按需安装某个入口时，必须同时安装兼容的 V2 `mdf-core`；
`mdf-init-repo` 和 `mdf-review-doc` 还必须同时安装 `mdf-grill`。

## 测试

MDF 测试只依赖 Python 标准库、Git 和 pytest：

```bash
python -m pip install -r tests/requirements-test.txt
python -m pytest
```

测试范围和说明见 [tests/README.md](./tests/README.md)。
