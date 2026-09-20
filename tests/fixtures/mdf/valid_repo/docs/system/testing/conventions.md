---
title: "测试约定"
doc_type: system-testing
evidence:
  - path: GLOSSARY.md
    verification: "对照夹具术语页确认本页不复述产品行为"
---

# 测试约定

本夹具仅有 `check` 自定义验证项，未按 UT、PT、IT、E2E 分层。命令非零退出为
失败；未配置将 warning、deprecated 或 notice 当失败。禁止用 skip 降低门槛。
