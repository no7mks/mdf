---
title: "测试约定"
doc_type: system-testing
evidence:
  - path: PROJECT.md
    verification: "对照验证卡片与本页 kind、失败语义、skip 是否同义"
---

# 测试约定

本页是项目级测试规则的起步叶。命令表仍以 `PROJECT.md` 验证卡片与
`.mdf/manifest.yaml` 为准，不在此复述。主题混杂或超过 450 行时拆到
`kinds.md`、`failure.md`、`suites.md`、`environment.md`；本页改为链接。

## Kind 与选用

`verification.commands` 的 `kind` 只是标签。UT、PT、IT、E2E 的选用规则写在
本页；尚未有对应测试时不把该 kind 写成已采用。

## 失败语义

命令非零退出为失败。warning、deprecated、notice 是否当失败，以各验证命令的
配置为准，并在本页写明；未写明不得假定。

## skip

禁止用 skip 降低已声明门槛或逃避分层。允许的 skip 须写明原因。xfail 与预期
失败同样记录。

## 分层

`verification.suites` 的映射以 manifest 为准。本页只写何种测试进 `quick`、
交付 suite 或只进 `full` 的规则；尚未分层则全部项同等。
