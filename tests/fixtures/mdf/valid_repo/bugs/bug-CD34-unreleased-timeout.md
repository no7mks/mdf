---
id: bug-CD34
type: bug
status: ready
severity: major
found_in: unreleased
---

# Unreleased timeout

## 观察到的行为

尚未发布的调用路径可能超时。

## 期望行为

调用应在限定时间内返回。

## 复现步骤

运行尚未发布的超时用例。

## 影响

开发版本的验证会失败。

## 所需回归证据

增加覆盖该调用路径的自动化测试。
