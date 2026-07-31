---
title: "Data model"
doc_type: system-data
evidence:
  - path: src/service.py
    verification: "读取数据结构并运行 python -m pytest"
---

# Data model

服务不持有持久化数据，仅处理内存中的健康状态。
