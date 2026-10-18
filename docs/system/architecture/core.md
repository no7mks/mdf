# MDF Core 的职责边界

本页说明 `skills/mdf/scripts/mdf_core/` 的 package 划分与命令组装入口。

## Package 职责

每个 package 按当前承担的职责组织，子 package 独立计数。

| package | 职责 | 关键模块 |
| --- | --- | --- |
| 根 | CLI 参数、命令组装与公共命令适配 | `cli`、`commands_misc` |
| `foundation` | 共享类型、错误、路径、文本与 YAML | `errors`、`paths`、`yamlutil` |
| `documents` | Proposal、Bug、HTML 工作材料及对象操作 | `proposals`、`prp_split`、`html_documents` |
| `inspection` | 仓库、事实、evidence、体积与结构检查 | `doctor`、`audit`、`code_size` |
| `lifecycle` | 交付身份、roster、阶段、版本收口与发布 | `delivery_state`、`roster`、`closeout_stage` |
| `execution` | module 验证配置、命令执行与测试报告 | `modules`、`module_verify`、`verify_run`、`reports` |
| `workspace` | Git、worktree、初始化、同步、hook 与安装维护 | `gitflow`、`gitutil`、`init_repo`、`upgrade` |
| `integrations` | CodeWiki 运行时与跨工作区联调通道 | `codewiki_runtime`、`integrate` |

## 入口与依赖

命令入口负责组合各领域能力，领域模块通过明确的 import 引用实际定义。

- 用户命令入口仍为 `skills/mdf/scripts/mdf.py`，由 `mdf_core.cli` 组装命令。
- 共享类型与解析工具位于 `foundation`；跨 package 调用使用完整模块路径。
- 已迁移模块不在根目录保留 facade 或 re-export；测试的 import 与 monkeypatch 指向实际定义。
- 模板读取从 Skill 根的 `assets/templates/` 定位；不依赖调用方 cwd。
- package 大小按 [仓库契约](../../../skills/mdf/references/repository-contract.md) 检查。
  - 实现与测试分别计数，每类最多 50；超限按设计职责拆分后各结果每类最多 35。
  - 子 package 独立计数，module ignore 命中的源文件排除。
