"""唯一 MDF Skill 的入口与内部工作流契约测试。"""

from __future__ import annotations

from conftest import skill_dir


def workflow(name: str) -> str:
    return (skill_dir("mdf") / "workflows" / f"{name}.md").read_text(
        encoding="utf-8"
    )


def test_mdf_is_the_only_public_skill_and_dispatches_commands() -> None:
    skill = skill_dir("mdf")
    entry = (skill / "SKILL.md").read_text(encoding="utf-8")

    assert [path.name for path in skill.parent.iterdir() if path.is_dir()] == [
        "mdf"
    ]
    for command in (
        "init",
        "start",
        "review-doc",
        "finish",
        "audit",
        "archive",
        "grill <议题>",
    ):
        assert command in entry
    assert "裸 `$mdf`" in entry
    assert "workflows/<intent>.md" in entry
    assert "$mdf <intent>" in entry
    assert "mdf.py\" <command>" in entry
    assert "版本化文档与交付流程" in entry
    assert "已确认决策与`当前事实文档`分开" in entry
    assert "可验证的演进记录" in entry


def test_init_and_review_load_internal_contracts() -> None:
    init = workflow("init")
    review = workflow("review-doc")
    common = workflow("common")

    assert "repository-contract.md" in init
    assert "workflows.md" not in init
    assert "形成`初始化方案`" in init
    assert "再次显式调用 `$mdf init`" in init
    assert "docs/research/" in init
    assert "## 1. 入口检查" in init
    assert "## 2. 盘点与归类" in init
    assert "## 5. 续办" in init
    assert "没有未说明的遗留文件" in init
    assert "README 只作导航" not in init
    assert "`README.md`、`PROJECT.md`、`AGENTS.md` 与 `GLOSSARY.md`" in init
    assert "各自符合`根文档职责`" in init
    assert "检查项目原有的全部文档" in init
    assert "项目原有文档\n   仅可按`初始化方案`归位、保留或排除" in init
    inventory = init.split("## 2. 盘点与归类", maxsplit=1)[1].split(
        "## 3. 落地初始化方案", maxsplit=1
    )[0]
    assert "不做`事实复核`" in inventory
    assert "`evidence`" not in inventory
    assert "仅在外层工作流入口检查一次" in common
    assert "不得重复 clean 检查而拒绝修改" in common
    assert "object-contract.md" in review
    assert "内部 grill 工作流" in review
    assert "closed 或 archive 对象拒绝修改" in review


def test_repository_contract_defines_static_core_terms() -> None:
    skill = skill_dir("mdf")
    contract = (skill / "references" / "repository-contract.md").read_text(
        encoding="utf-8"
    )
    init = workflow("init")

    assert "## 核心术语" in contract
    for term in (
        "`当前事实文档`",
        "`事实复核`",
        "`审阅`",
        "`validation`",
        "`evidence`",
        "`基线`",
        "`验证命令`",
        "`initializing`",
        "`ready`",
    ):
        assert term in contract
    terms = contract.split("## 固定布局", maxsplit=1)[0]
    assert "`audit`" not in terms
    assert "`init`" not in terms
    assert "`finish`" not in terms
    assert "closeout 时执行" not in terms
    assert "`全量审阅`" not in contract
    assert "`范围审阅`" not in contract
    assert "`当前事实文档`" in init
    assert "`validation`" in init
    assert "`全量审阅`" in init


def test_repository_contract_defines_root_document_responsibilities() -> None:
    skill = skill_dir("mdf")
    contract = (skill / "references" / "repository-contract.md").read_text(
        encoding="utf-8"
    )

    assert "## 根文档职责" in contract
    assert "`README.md` 面向项目用户与维护者" in contract
    assert "`PROJECT.md` 仅面向项目维护者" in contract
    assert "`AGENTS.md` 仅面向在仓库中工作的 Agent" in contract
    assert "要求 Agent 先读 `README.md`" in contract
    assert "`GLOSSARY.md` 面向所有读者维护稳定的领域词典" in contract


def test_contracts_do_not_duplicate_workflow_steps() -> None:
    skill = skill_dir("mdf")
    object_contract = (skill / "references" / "object-contract.md").read_text(
        encoding="utf-8"
    )

    assert not (skill / "references" / "workflows.md").exists()
    assert "$mdf " not in object_contract
    assert "release-closeout" not in object_contract
    assert "finish 时" not in object_contract


def test_audit_is_reused_without_delivery_logic() -> None:
    audit = workflow("audit")
    init = workflow("init")
    finish = workflow("finish")

    assert "只读" in audit
    assert "执行`全量审阅`" in audit
    assert "`事实复核`" in audit
    assert "从文档到实现" in audit
    assert "从实现到文档" in audit
    assert "## 审阅类型" in audit
    assert "`全量审阅`：从文档和实现两个方向" in audit
    assert "`范围审阅`：从文档和实现两个方向" in audit
    assert "`全量审阅`" in audit
    assert "`范围审阅`" in audit
    assert "`develop...HEAD`" not in audit
    assert "`master...HEAD`" not in audit
    assert "`release-closeout`" not in audit
    assert "`audit` 执行`全量审阅`" in init
    assert "## 交付前检查" in finish
    assert "内部委托 `audit`" in finish
    assert "release 执行`全量审阅`" in finish


def test_start_and_finish_define_strict_gitflow_operations() -> None:
    start = workflow("start")
    finish = workflow("finish")

    assert "master" in start and "develop" in start
    assert "推送到 origin 并设置 upstream" in start
    assert "no-ff 合并到 develop" in finish
    assert "no-ff 合并到" in finish and "master" in finish
    assert "原子 push" in finish
    assert "v<semver>" in finish
