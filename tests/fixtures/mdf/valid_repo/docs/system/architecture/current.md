---
title: "Current architecture"
doc_type: system-architecture
evidence:
  - path: src/service.py
    verification: "读取模块结构并运行 python -m pytest"
---

# Current architecture

单个服务模块公开健康检查函数。
