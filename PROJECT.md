# PROJECT.md

本文件面向 MDF 维护者，记录本仓库的开发、验证与维护约束。

## 项目边界

- MDF 仅实现当前契约；不得在 Skill、文档、模板、脚本或测试中引入、描述或维护旧版
  MDF/V1 的兼容、迁移、识别或运行时分支。
- 不符合当前契约的既有内容只按当前初始化写入流程处理；不得推断或保留旧版语义。

## 本地验证

MDF 测试只依赖 Python 标准库、Git、pytest 和 pytest-xdist：
`python -m pip install -r tests/requirements-test.txt`。

| 入口 | 命令 | 何时跑 |
| --- | --- | --- |
| lint | `python -m pytest tests/lint` | 任何改动 |
| build | `python -m compileall -q skills/mdf/scripts` | 任何改动 |
| quick | `python -m pytest tests/unit` | 任何改动 |
| smoke | `python -m pytest tests/unit tests/e2e -m 'not release_only'` | 改动收口 |
| release | `python -m pytest tests/unit tests/e2e` | 发布前 |

named suite 指 gitflow、planning 等具体的自定义 suite，不是一个聚合入口。
改动某功能块时须验证相应 suite；smoke 或 release 已完整覆盖时不重复运行，从同一份 JUnit 提取结果。
smoke 未覆盖的 release_only 成员不得声称通过；确需验证时只补跑缺失范围。成员、复用规则与预算见
[docs/system/testing/conventions.md](docs/system/testing/conventions.md)。
`pytest.ini` 默认 `-n auto --maxprocesses=4` 并行，只在点名调试时用 `-n0`。

## 发布与安装

- 只关注当前 MDF 发布后的可用性，不保留、解释、检测或兼容历史版本。
- `install` 要求源仓库工作区干净，并只归档当前 `HEAD`。
  - 修订写入 `<安装根>/versions/<commit>/`，再原子切换 `current`。
  - 未传 `--home` 且未设置 `MDF_HOME` 时，安装根是 `~/.local/share/mdf`。
  - `MDF_HOME` 无效时停止，不回退到默认路径。
- `$mdf upgrade` 更新本机安装。自检失败回滚到切换前的 `current`。
  - 除补齐仓库根 `.gitignore` 外不修改业务仓，不重写 `AGENTS.md`。
- `mdf detach` 只移除业务仓里已跟踪的 Skill 副本。
- ❌ install、upgrade 与 detach 都不得删除目标仓库的 `.mdf/` 或 `docs/`。

## 文件规模

- Skill、脚本、测试及其手写文本只设硬限制，字符按显示宽度计，中文及其他全角、宽字符算 2 个：
  - 单行最多 180 字符。
  - 源代码、测试源代码单文件最多 1000 行；其他手写文本最多 500 行。
  - package 按目录直属文件计数，实现与测试分开；每类最多 50 个，超限按设计职责拆至每类最多 35 个。
  - HTML 不受文件行数限制。
- 文件拆分遵守 `skills/mdf/references/repository-contract.md` 的职责与结构规则。
  - 代码从职责、依赖方向与适用的设计模式确定边界；文档从主题、读者与信息结构确定边界。
  - 不得按行数机械切成 `part1`、`part2`，也不得仅改名掩盖机械切分。
  - 合理设计允许迁移入口，不强求在原位置保留 facade；同步更新调用方、测试与文档引用。
- 超限必须拆分，拆分后的每个结果不得超过对应硬限制的 70%，整数向下取整。
  - 单行拆分后最多 126 字符；代码文件拆分后每个最多 700 行；其他文本最多 350 行。
  - 不允许用删除空行、压缩内容或声明不拆分理由来规避拆分。
- lint 检查当前硬限制（含 package 文件数）；审查按修改前内容复核超限后的拆分结果。

## 文档结构

MDF 自身的 Markdown 与目标仓库文档共用一套结构规则，定义见
`skills/mdf/references/doc-structure.md`。MDF 自身范围包括 Skill、intent、模板、`docs/` 与根文档。

- 文档格式与表达尽量遵循 ASD-STE100；简体中文的适用方式与写作约定见上述规则。
- 硬限制由 `tests/lint/test_prose_structure.py` 检查，与目标仓库 fact audit 的
  `prose.*` finding 使用同一分析器。
- 尚未改写的文件列在 `tests/lint/prose_baseline.txt`，只减不增：
  - 不在清单中的文件必须满足硬限制。
  - 清单中的文件一旦达标，lint 要求把它移出清单。
- 内容形态与超限后的 70% 拆分要求由审查确认。

## 文案语言

- 面向读者的说明性文本使用简体中文；schema 键、命令、路径、文件名和代码标识符
  保持原样。
- 常用英文可以保留；不属于此范围的领域英文术语必须在 `GLOSSARY.md` 中定义。

## 文档地图

- [README.md](README.md)：面向使用者的项目入口。
- [GLOSSARY.md](GLOSSARY.md)：MDF 领域术语。
- [Core 职责边界](docs/system/architecture/core.md)：源码 package 划分与依赖入口。
- [docs/system/interfaces/mdf-cli.md](docs/system/interfaces/mdf-cli.md)：本仓库
  `mdf.py` 的调用约定与命令总表，分页记录参数与实际副作用；不随 Skill 安装。
- [docs/system/testing/conventions.md](docs/system/testing/conventions.md)：测试层级、
  失败语义、报告与各 suite。
