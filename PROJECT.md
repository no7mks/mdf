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
| smoke | `python -m pytest tests/unit tests/e2e` | 改动收口 |
| release | `python -m pytest tests/unit tests/e2e` | 发布前 |

改动某功能块时另跑其 named suite；各 suite、预算、失败语义与报告见
[docs/system/testing/conventions.md](docs/system/testing/conventions.md)。
`pytest.ini` 默认 `-n auto` 并行，只在点名调试时用 `-n0`。

## 发布与安装

- 只关注当前 MDF skill set 发布后的可用性，不保留、解释、检测或兼容历史版本。
- `install`：只在目标 Agent Skills 目录中尚无 `mdf` 时运行。
  - 从干净工作区的 `HEAD` 写入当前发布内容。
  - 在 `references/.version` 写入完整 commit hash。
  - 维护者升级须先运行 `unistall`。
  - 已安装项目可用 `$mdf upgrade` 从上游默认分支替换已安装 Skill，并更新已有
    `AGENTS.md` 的 MDF 托管区块。
- `diff`：以该 commit 为基线，分别比较本地与目标。
- ⚠️ install、diff 与 upgrade 都不得删除目标仓库的 `.mdf/` 或 `docs/` 产出物。

## 文件规模

- Skill、脚本、测试及其手写文本只设硬限制，字符按显示宽度计，中文及其他全角、宽字符算 2 个：
  - 单行最多 180 字符。
  - 源代码、测试源代码单文件最多 1000 行；其他手写文本最多 500 行。
  - HTML 不受文件行数限制。
- 超限必须拆分，拆分后的每个结果不得超过对应硬限制的 70%，整数向下取整。
  - 单行拆分后最多 126 字符；代码文件拆分后每个最多 700 行；其他文本最多 350 行。
  - 不允许用删除空行、压缩内容或声明不拆分理由来规避拆分。
- lint 检查当前硬限制；审查按修改前内容复核超限后的拆分结果。

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
- [docs/system/interfaces/mdf-cli.md](docs/system/interfaces/mdf-cli.md)：本仓库
  `mdf.py` 的调用约定与命令总表，分页记录参数与实际副作用；不随 Skill 安装。
- [docs/system/testing/conventions.md](docs/system/testing/conventions.md)：测试层级、
  失败语义、报告与各 suite。
