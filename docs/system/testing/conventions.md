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
- macOS 的 PATH 命中 `/usr/bin/git` 时，测试启动阶段用 `xcrun --find git` 定位当前 toolchain，
  将其目录置于本次测试进程的 PATH 首位，省去每次 Git 调用的启动器开销。
  - 仍执行真实 Git；自选 Git 与其他平台保持原 PATH。解析失败或目标不可执行时保持原 PATH。
- pytest 临时目录按 checkout 路径隔离在系统临时目录的 `mdf-pytest-<路径摘要>/` 下。
  - 保留 pytest 原有的保留数量与清理策略，避免跨项目清理临时仓库。
  - 显式 `--basetemp` 或 `PYTEST_DEBUG_TEMPROOT` 优先；不改用户的全局环境。
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

在仓库根执行；pytest 默认 `-n auto --maxprocesses=4 --dist worksteal` 并行。
并发上限为 4，减少大量 Git 子进程并发时的资源竞争；如需提高，须同时指定 `-n N --maxprocesses=N`。
用时为本机并行实测。

| 入口 | 命令 | 预算 | 实测 | 何时跑 |
| --- | --- | --- | --- | --- |
| lint | `python -m pytest tests/lint` | 无 | 约 2s | 任何改动 |
| build | `python -m compileall -q skills/mdf/scripts` | 无 | <1s | 任何改动 |
| quick | `python -m pytest tests/unit` | 30s | 约 6s | 任何改动 |
| smoke | `python -m pytest tests/unit tests/e2e -m 'not release_only'` | 300s | 按报告核对 | 改动收口 |
| release | `python -m pytest tests/unit tests/e2e` | 无 | 按报告核对 | 发布前 |

全部 test case 的检查命令为 `python -m pytest`，等于 lint 与 release 之和，没有单独入口。

### smoke 与 release 的成员

- quick、smoke、release 是有固定用途的保留 suite；smoke 包含全部 quick，release 包含全部 smoke。
- `release_only` 是 test case 的成员标记，不是 skip；按测试文件标记完整的重型恢复或竞态矩阵。
  - 当前覆盖 `test_sync_pr.py`、`test_pr_recovery.py`、`test_pr_remote_cleanup.py` 三个 PR 矩阵文件。
  - smoke 排除这些文件；release 与完整 gitflow suite 仍执行全部成员，不删除测试或减弱断言。
  - smoke 保留 `test_pull_finish.py` 的常规 PR 收口，以及 `test_sync_pr_smoke.py` 的 master/GitHub 与 develop/GitLab 主路径。
- 调整成员须结合耗时报告和覆盖职责，保留主路径；收口时核对 smoke 的实际耗时，不通过放宽预算解决超时。

## 项目自定义 suite（named suite）

每个 suite 都有具体名称；named suite 是 gitflow、planning 等自定义 suite 的统称，不是额外的大集合或执行入口。
按功能块划分；改动某功能块时验证对应 suite，涉及多个功能块则逐个报告实际名称及结果。

- 命令：`python -m pytest tests/unit/<suite> tests/e2e/<suite>`。
- 没有 `tests/unit/<suite>` 的 suite 只跑 `tests/e2e/<suite>`。
- 开发时可运行对应 suite；smoke 或 release 已完整覆盖时复用报告，不重复运行。
- 各 suite 可以重叠，不要求自定义 suite 是 smoke 的子集；不能把所选多个 suite 的合计称为一次 named suite。

| suite | 含 `tests/unit/<suite>` | 覆盖 |
| --- | --- | --- |
| delivery | 是 | delivery、roster、verification、verify_run、reports、project_verify、worktree_check |
| gitflow | 是 | gitflow、publish、git_ops、gitutil、merge-no-ff |
| closeout | 是 | closeout_*、commands_release、semver、validate_release |
| planning | 否 | planning、prp_split、tree_view、list_objects、proposals |
| objects | 是 | bugs、archive、moves、jot、make-id、对象校验、yamlutil |
| docs | 是 | audit、doctor、validate_*、doc_size、codewiki_runtime |
| init | 是 | init_repo、commands_misc、prepare-git、bootstrap |
| integrate | 否 | integrate、integrate_http、integrate_store |
| deploy | 否 | `mdf-deploy.sh`、upgrade |

### 复用已有报告

- 同一代码、测试及验证配置状态下，smoke 或 release 包含所需 suite 的全部成员时，
  必须从该次 JUnit XML 提取结果，不再单独运行该 suite，也不并行重复执行已覆盖的成员。
- 先核对 suite 的成员规则、运行命令、退出码与报告完整性；额外过滤、取消或未执行全部成员的运行不算完整覆盖。
  - smoke 失败时先读原报告及捕获输出；不得为查看输出重跑 named suite，也不得把其中失败项报告为通过。
  - 未覆盖的成员，或后续实现、测试、验证配置变化导致结果失效时，只补跑所需范围。
  - 例如 smoke 只覆盖 gitflow 的非 release_only 成员，须注明部分覆盖；相关改动需完整 gitflow 时只补剩余成员。
- 按 `<testcase classname>` 的模块路径筛选本页表格对应目录：
  - 例如 gitflow 选取 `tests.unit.gitflow.` 与 `tests.e2e.gitflow.` 前缀；planning 只取 `tests.e2e.planning.`。
  - 保留参数化 test 的每个实例，统计 total、passed、failures、errors、skipped；空集合不得算通过。
  - 同时给出所覆盖目录、完整或部分覆盖与原 JUnit 路径，注明实际运行的 suite，不声称另跑过其他 suite。
- 可汇总成员的 `time` 作为 test 累计用时；并行 test 用时之和不等于 suite 的实际耗时。
  - smoke 的预算仍按该次运行的实际耗时核对；不把提取的累计用时当作独立 suite 的预算证据。

## 点名执行

只用于定位：`python -m pytest -n0 tests/e2e/delivery/test_roster.py::<test 名>`。
