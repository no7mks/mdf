# 静态检查 Benchmark

## 复现

```bash
python internal/benchmark_check.py --baseline ed6d4d11cbe1543988f39eb605e3e99780ebc732 \
  --ig-repo ../integration-gate --ig-revision e230da1287cbe202cdeab2d2814d0d55e428553f
```

- 合成仓在 valid_repo fixture 上增加 200 份源码和 40 页事实，含一次 merge commit。
  两个分支分别变更一份源码及一页事实，再汇入同一目标。
- IG 使用指定 commit 的临时 checkout，依次提交 `src/ig_config.py` 与配置事实页的最小改动。
  兄弟仓库只用于读取 Git 对象。
- cold 每轮新建 checkout；warm 复用同一 checkout。两者均启动新 Python 进程，保留 OS cache。
- 每项 5 轮。JSON 输出原始 wall time、median、nearest-rank p95、Python 启动时间、扣除启动后的时间、findings 与退出码。

## 实测

单位为秒。每格为 median / p95，括号内为扣除 Python 启动时间后的数值。

| 输入 | 缓存 | 原 entry | entry | 原 branch quick | dev branch |
| --- | --- | --- | --- | --- | --- |
| 合成仓 | cold | 0.756/0.790 (0.741/0.776) | 0.230/0.256 (0.215/0.241) | 0.988/1.001 (0.974/0.988) | 0.330/0.336 (0.315/0.323) |
| 合成仓 | warm | 0.733/0.773 (0.719/0.759) | 0.233/0.237 (0.219/0.224) | 0.971/0.988 (0.958/0.974) | 0.310/0.315 (0.296/0.302) |
| IG | cold | 3.409/3.596 (3.397/3.584) | 0.252/0.254 (0.240/0.242) | 2.692/2.732 (2.680/2.719) | 0.505/0.519 (0.493/0.506) |
| IG | warm | 3.597/3.620 (3.585/3.608) | 0.247/0.254 (0.235/0.241) | 2.657/2.686 (2.645/2.675) | 0.475/0.480 (0.462/0.468) |

- entry 和 dev 退出 0，无 blocking finding。两档跳过 stale。原 entry 也退出 0，并报告 stale。
- 两个输入的 strict 新旧退出码均为 2，findings multiset 完全相同。
- closeout 与原 branch quick 均退出 2，固有 findings 相同，都是 `evidence.stale`。
  - 合成仓 1 项，`docs/system/interfaces/entry-000.md` 引用 `src/entry_000.py`。
  - IG 6 项，引用 `src/ig_config.py`。接口页为 `config-loader`、`errors`、`runner-scheduler` 与 `test-review`。
    用户指南页为 `load-configuration` 与 `use-result-delivery`。
