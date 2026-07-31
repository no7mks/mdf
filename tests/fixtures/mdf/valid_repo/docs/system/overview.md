---
title: "System boundary"
doc_type: system-boundary
evidence:
  - path: src/service.py
    verification: "读取服务入口并运行 python -m pytest"
---

# System boundary

系统由仓库内的服务模块组成，不依赖外部服务。
