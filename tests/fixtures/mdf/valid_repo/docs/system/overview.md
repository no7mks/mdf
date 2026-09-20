---
title: "System boundary"
doc_type: system-boundary
evidence:
  - path: src/service.py
    verification: "读取服务入口并运行 python -m pytest"
---

# System boundary

系统由仓库内的服务模块组成，不依赖外部服务。

## 核心模块

| 模块 | 打开 |
| --- | --- |
| 配置 | 不适用：此夹具无运行时配置面 |
| 可观测性 | 不适用：此夹具无可观测实现 |
| 错误 | 不适用：此夹具无独立错误模型 |
| 鉴权 | 不适用：此夹具无鉴权面 |
| 限制与恢复 | 不适用：此夹具无运行限制或恢复面 |
