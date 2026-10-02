# MDF 仓库测试约定

本页是 MDF 仓库自身测试的唯一说明：层级、kind、失败语义、报告与各 suite。约定本身
见 `skills/mdf/references/delivery-contract.md`「测试层级与分类」至「验证 suite」。

## 层级与 kind

- test 是 `test_*` 函数；test case 是一个测试文件，报告中的 `classname` 即其模块路径。
- `tests/lint/`：Skill 文档、契约文本、模板与文件规模检查，属于 lint 入口，不是 suite 成员。
- `tests/unit/<功能块>/`：直接调用 `mdf_core` 的 UT；PT 以固定种子的 `random`
  生成输入（如 `test_semver_rules.py`、`test_yaml_subset.py`）。
- `tests/e2e/<功能块>/`：在临时 Git 仓库中以子进程调用 `mdf.py` 或 `mdf-deploy.sh`
  的 CLI E2E。
- 全部测试 hermetic：只依赖 Python 标准库、Git、pytest 与 pytest-xdist，不访问网络。
- 共用 helper：
  - `mdf_test_support.py`：fixture 仓库与 CLI 调用。
  - `support_delivery.py`、`support_upgrade.py`、`support_planning.py`、`support_routes.py`：
    各功能块 E2E 的准备与文档解析。
  - `fixtures/mdf/valid_repo/`：合成仓库。

## 失败语义

- `pytest.ini` 的 `filterwarnings = error` 让 warning、deprecated 失败；
  `--strict-markers` 拒绝未注册 marker；`xfail_strict = true`。
- `tests/conftest.py` 在出现 skipped、xfailed 或 xpassed 时把退出码改为失败。
- 未选中任何 test 时 pytest 以退出码 5 失败。
- 豁免：无。

## 报告

每次运行都写 JUnit XML，`junit_logging = all` 让报告带上各 test 捕获的输出。

| 情形 | 位置 |
| --- | --- |
| 设了 `MDF_REPORT_DIR` | `$MDF_REPORT_DIR/junit.xml` |
| 未设 | `.test-reports/<UTC 时间戳>-<pid>/junit.xml` |
| 测试中对未接入 MDF 的临时目录调用 CLI | 运行日志写到 `.test-reports/mdf-logs/` |

- `.test-reports/` 已被 `.gitignore` 忽略，每次运行清理 7 天前的条目。
- ⚠️ 失败时先读报告中的 `<failure>` 与捕获输出，不为看输出而重跑。
- pytest 入口读 JUnit，不另 tee。`compileall` 等无报告命令才 tee 到 `.test-reports/`。

## 入口

在仓库根执行；pytest 默认 `-n auto --dist worksteal` 并行。用时为本机并行实测。

| 入口 | 命令 | 预算 | 实测 | 何时跑 |
| --- | --- | --- | --- | --- |
| lint | `python -m pytest tests/lint` | 无 | 约 2s | 任何改动 |
| build | `python -m compileall -q skills/mdf/scripts` | 无 | <1s | 任何改动 |
| quick | `python -m pytest tests/unit` | 30s | 约 6s | 任何改动 |
| smoke | `python -m pytest tests/unit tests/e2e` | 300s | 约 42s | 改动收口 |
| release | `python -m pytest tests/unit tests/e2e` | 无 | 约 42s | 发布前 |

全部 test case 的检查命令为 `python -m pytest`，等于 lint 与 release 之和，没有单独入口。

## named suite

按功能块划分；改动某功能块时运行其 named suite，改动涉及几个就跑几个。

- 命令：`python -m pytest tests/unit/<suite> tests/e2e/<suite>`。
- 没有 `tests/unit/<suite>` 的 suite 只跑 `tests/e2e/<suite>`。

| suite | 含 `tests/unit/<suite>` | 覆盖 |
| --- | --- | --- |
| delivery | 是 | delivery、roster、verification、verify_run、test_reports、project_verify、worktree_check |
| gitflow | 是 | gitflow、publish、git_ops、gitutil、merge-no-ff |
| closeout | 是 | closeout_*、commands_release、semver、validate_release |
| planning | 否 | planning、prp_split、tree_view、list_objects、proposals |
| objects | 是 | bugs、archive、moves、jot、make-id、对象校验、yamlutil |
| docs | 是 | audit、doctor、validate_*、doc_size、codewiki_runtime |
| init | 是 | init_repo、commands_misc、prepare-git、bootstrap |
| integrate | 否 | integrate、integrate_http、integrate_store |
| deploy | 否 | `mdf-deploy.sh`、upgrade |

## 点名执行

只用于定位：`python -m pytest -n0 tests/e2e/delivery/test_roster.py::<test 名>`。
