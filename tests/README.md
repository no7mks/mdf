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

`test_skill_structure.py` 对 `skills/` 下的每个 MDF Skill 自动执行结构检查；
`fixtures/mdf/valid_repo/` 是协议测试使用的合成仓库。
