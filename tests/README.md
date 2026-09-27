# MDF 测试

本目录验证 Mars Docs
Flow 的技能契约和确定性 CLI。测试在临时 Git 仓库中运行，覆盖 manifest、ID、SemVer、Gitflow、工作对象、审计、归档、
链接重写和 release/hotfix
closeout。

## 运行

```bash
python -m pip install -r tests/requirements-test.txt
python -m pytest
```

`pytest.ini` 默认以 `-n auto --dist worksteal` 并行运行（pytest-xdist）；
调试单个测试可加 `-n0`。

`test_skill_structure.py` 对 `skills/` 下的每个 MDF Skill 自动执行结构检查；
`fixtures/mdf/valid_repo/` 是协议测试使用的合成仓库。

`test_mdf_bootstrap.py` 验证空仓库和工程模板共用初始化 CLI、无事实页及无远端时
完成 ready 与本地分支准备；新旧项目的语义分流由 intent 执行，不由 CLI 推断。

## 交付流程与规划

- `test_mdf_roster.py`：start 冻结人数与策略、named roster 展开、人数抬升、
  winner / partition 集成、design 后锁定 qa/dev strategy，以及 0,0 在 owner
  上写测试。
- `test_mdf_delivery.py`：设计基线、并行交接、收敛与审查权限、内容指纹失效、
  原地补齐 Change 及 Gitflow 冲突。
- `test_mdf_verification_layers.py`：lint / build / quick / smoke / full 的门禁、预算与证据。
- `test_mdf_doc_loading.py`：`docs/user-guide/` doc_type、`docs/context/adr/`、
  `layout.migrate` / `layout.testing` / `manifest.schema` 指向 migrate、按角色行数硬限制，以及
  fact-audit `--scope branch` 的范围映射。
- `test_mdf_planning.py`：具名 verification、混态依赖树、milestone 依赖、拆分预检与失败恢复。
- `test_mdf_planning_workspace.py`：常驻 planning 工作区与合入 develop。
- 发布测试同时覆盖 implemented → released、过程材料留存与 Proposal 链接重写。
