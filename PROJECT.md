# PROJECT.md

本文件面向 MDF 维护者，记录本仓库的开发、验证与维护约束。

## 项目边界

- MDF 仅实现当前契约；不得在 Skill、文档、模板、脚本或测试中引入、描述或维护旧版
  MDF/V1 的兼容、迁移、识别或运行时分支。
- 不符合当前契约的既有内容只按当前初始化写入流程处理；不得推断或保留旧版语义。

## 本地验证

MDF 测试只依赖 Python 标准库、Git 和 pytest：

```bash
python -m pip install -r tests/requirements-test.txt
python -m pytest
```

改动某项协议或工作流时，先运行对应测试，再运行完整测试集。

## 发布与安装

- 只关注当前 MDF skill set 发布后的可用性，不保留、解释、检测或兼容历史版本。
- 安装或升级时，先卸载目标 Agent skills 目录中的旧 `mdf-*` Skill 与 `mdf`，再安装
  当前发布内容；不得删除目标仓库的 `.mdf/` 或 `docs/` 产出物。

## 文件规模

- Skill、脚本、测试及其手写文本的单行软阈值为 80 字符，单文件软阈值为 400 行。
- 单行超过 120 字符或单文件超过 500 行必须使检查失败。

## 文档地图

- [README.md](README.md)：面向用户和维护者的项目入口。
- [GLOSSARY.md](GLOSSARY.md)：MDF 领域术语。
- [docs/product/reference/mdf-cli.md](docs/product/reference/mdf-cli.md)：CLI 参考。
- [tests/README.md](tests/README.md)：测试结构与 fixture 说明。
