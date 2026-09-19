# 项目维护

本文件面向项目维护者（含 Agent），是 `AGENTS.md` 之后的第一份项目文档。

## 验证卡片

Agent 执行维护改动时只读本节。以表格列出环境要求与 lint、test、build、
CI 等价检查命令；命令以仓库配置和脚本为准。

| 命令 | 预期结果 |
| --- | --- |
| 待填 | 待填 |

## 技术栈

一行级列出语言、构建与主要运行时；细节下沉到 `docs/system/`。

## 维护约束

记录项目专属的目录、生成物、发布和维护约束。仅维护者需要的内容写在本文件或
下沉到 `docs/system/`，不写入根 `README.md`。运行时配置属于
`docs/system/operations/configuration.md`。接口、数据与运行时行为不复述
`docs/system/` 事实页，只保留指向对应页面的链接。

## 目录约定

- 记录 `src/` 中的业务实现、`tests/` 中的测试和生成物目录。
- 仅列出允许处于仓库顶层的例外项目项及其理由。

## 文档入口

- 系统入口：`docs/system/overview.md`
- 全库任务地图：`docs/README.md`
