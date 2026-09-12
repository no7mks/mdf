# PROJECT.md

本文件面向 MDF 维护者，记录本仓库的开发、验证与维护约束。

## 项目边界

- MDF 仅实现当前契约；不得在 Skill、文档、模板、脚本或测试中引入、描述或维护旧版
  MDF/V1 的兼容、迁移、识别或运行时分支。
- 不符合当前契约的既有内容只按当前初始化写入流程处理；不得推断或保留旧版语义。

## 本地验证

MDF 测试只依赖 Python 标准库、Git、pytest 和 pytest-xdist：

```bash
python -m pip install -r tests/requirements-test.txt
python -m pytest
```

`pytest.ini` 默认 `-n auto` 并行；全量验证不要加 `-n0` 串行。调试单个测试时才用 `-n0`。

改动某项协议或工作流时，先运行对应测试，再运行完整测试集。

验证输出中的 warning、skip、note 和 deprecated 都视为失败，必须处理后才能交付。

## 发布与安装

- 只关注当前 MDF skill set 发布后的可用性，不保留、解释、检测或兼容历史版本。
- `install` 只在目标 Agent Skills 目录中尚无 `mdf` 时从干净工作区的 `HEAD` 写入
  当前发布内容，并在 `references/.version` 写入完整 commit hash；维护者升级须先
  运行 `unistall`。已安装项目可用 `$mdf upgrade` 从上游默认分支替换已安装 Skill，
  并更新已有 `AGENTS.md` 的 MDF 托管区块。`diff` 以该 commit 为基线分别比较本地与
  目标。两者与 upgrade 都不得删除目标仓库的 `.mdf/` 或 `docs/` 产出物。

## 文件规模

- Skill、脚本、测试及其手写文本适用以下文件规模规则：
  - 列宽按显示宽度计，中文等宽字符算两个字符。80 是软限制；超过后可为了
    可读性尝试换行。120 是硬限制，超过必须换行；换行不得落在非标点位置。
  - 400 行是软限制；超过后可为了可读性拆分。500 行是硬限制；超过时必须评估
    是否拆分，若保留单文件，须在文件开头明确记载不拆分的理由。
- 自动检查执行列宽 120 和行数 500 的硬限制；软限制及拆分例外的理由由审查确认。

## 文案语言

- 面向读者的说明性文本使用简体中文；schema 键、命令、路径、文件名和代码标识符
  保持原样。
- 常用英文可以保留；不属于此范围的领域英文术语必须在 `GLOSSARY.md` 中定义。

## 文档地图

- [README.md](README.md)：面向用户和维护者的项目入口。
- [GLOSSARY.md](GLOSSARY.md)：MDF 领域术语。
- [docs/product/reference/mdf-cli.md](docs/product/reference/mdf-cli.md)：CLI 参考。
- [tests/README.md](tests/README.md)：测试结构与 fixture 说明。
