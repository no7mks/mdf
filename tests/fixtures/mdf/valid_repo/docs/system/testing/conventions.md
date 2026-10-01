---
title: "测试约定"
doc_type: system-testing
evidence:
  - path: GLOSSARY.md
---

# 测试约定

本夹具的 lint、build、quick、smoke、release 入口均为 `true`，尚无 UT、PT、IT、E2E
测试，也没有 named suite。非零退出、warning、notice、deprecated、skip、xfail、
xpass 与空选择都是失败；无豁免。
