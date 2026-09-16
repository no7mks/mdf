# 文档

本索引是 Agent 与维护者的任务地图：按任务打开对应的一两份文档，不通读目录。
当前事实排在决策与工作记录之前；只链接已有内容的页面，空目录不列出。

## 按任务找文档

| 任务 | 打开 |
| --- | --- |
| 了解系统能做什么、边界在哪 | [系统边界](system/overview.md) |
| 执行验证、了解目录例外 | [PROJECT.md](../PROJECT.md) |
| 修改或核对某部分当前行为 | `product/` 或 `system/` 下对应的一份事实页 |
| 处理指定 ID 的意图或偏差 | [proposals/](proposals/)、[bugs/](bugs/) 中对应文件 |

## 当前事实

产品与系统文档描述当前检出版本的行为，并引用仓库证据。只列出已存在的页面。

- 产品：[教程](product/tutorials/)、[操作指南](product/how-to/)、
  [参考](product/reference/)、[说明](product/explanation/)。
- 系统：
  - [系统边界](system/overview.md)
  - [架构](system/architecture/)
  - [接口](system/interfaces/)
  - [数据](system/data/)
  - [运行与运维](system/operations/)
  - [已知偏差](system/deviations.md)

## 决策

- [架构决策记录](adr/)：按主题打开单份，不把目录当阅读清单。

## 工作记录与调研

按 ID 或路径打开单个文件，不把本节目录当阅读清单。

- [随手记录](JOTS.md)：尚未分诊的原始记录。
- [proposals/](proposals/)：待实现意图及其状态记录。
- [bugs/](bugs/)：已观察到的偏差及其处理记录。
- [changes/](../changes/)：进行中与已交付的 Change，含随交付保存的目标、设计、gate 和验证材料；发布后归入版本目录。
- [context/research/](context/research/)：调研、候选方案和背景材料。
