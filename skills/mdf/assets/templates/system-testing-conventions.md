---
title: "测试约定"
doc_type: system-testing
evidence:
  - path: PROJECT.md
    verification: "对照验证卡片、manifest verification 与本页各 suite 的入口命令、预算是否一致"
---

# 测试约定

本页是项目级测试规则的起步叶。测试层级、kind、hermetic 与 suite 语义以 MDF
契约为准，本页只写本项目的落地规则。主题混杂或超过 450 行时拆到 `kinds.md`、
`failure.md`、`suites.md`、`environment.md`；本页改为链接。

## Kind 与归属

写明本项目 UT、PT、IT、E2E 各自的目录或 marker，以及 test case 如何归入各 suite。
尚未有对应测试时不把该 kind 写成已采用。

## 失败语义

命令非零退出为失败。warning、deprecated、notice 是否当失败，以各入口命令的
配置为准，并在本页写明；未写明不得假定。

## skip

禁止用 skip 降低已声明门槛或逃避分层。允许的 skip 须写明原因。xfail 与预期
失败同样记录。

## Suite

每个 suite 一节，写明目的、入口命令、成员选择规则、预算、环境，以及点名执行
test case / test 的命令模板。named suite 按同样格式追加。

### quick

只含 hermetic 的 UT 与 PT；任何改动都跑。

### smoke

包含 quick；feature、bugfix 收口时跑。

### release

包含 smoke，发版所需的 test case；release、hotfix 时跑。全部 test case 即 full，
通常没有入口。
