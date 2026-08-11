"""唯一 MDF Skill 的入口与内部 intent 契约测试。"""

from __future__ import annotations

from conftest import skill_dir


def intent(name: str) -> str:
    return (skill_dir("mdf") / "intents" / f"{name}.md").read_text(
        encoding="utf-8"
    )


def test_mdf_is_the_only_public_skill_and_dispatches_commands() -> None:
    skill = skill_dir("mdf")
    entry = (skill / "SKILL.md").read_text(encoding="utf-8")

    assert [path.name for path in skill.parent.iterdir() if path.is_dir()] == [
        "mdf"
    ]
    assert not (skill / "workflows").exists()
    for command in (
        "init",
        "codewiki generate",
        "codewiki update",
        "start",
        "jot",
        "jot promote",
        "doc derive",
        "doc create",
        "doc review",
        "doc archive",
        "finish",
        "audit",
        "grill <议题>",
    ):
        assert command in entry
    assert "裸 `$mdf`" in entry
    assert "intents/doc-create.md" in entry
    assert "intents/doc-derive.md" in entry
    assert "intents/doc-review.md" in entry
    assert "intents/doc-archive.md" in entry
    assert "intents/codewiki-generate.md" in entry
    assert "intents/codewiki-update.md" in entry
    assert "intents/jot.md" in entry
    assert "$mdf <intent>" in entry
    assert "mdf.py\" <command>" in entry
    assert "版本化文档与交付流程" in entry
    assert "已确认决策与`当前事实文档`分开" in entry
    assert "可验证的演进记录" in entry


def test_init_and_doc_intents_load_internal_contracts() -> None:
    init = intent("init")
    create = intent("doc-create")
    review = intent("doc-review")
    archive = intent("doc-archive")
    common = intent("common")

    assert "repository-contract.md" in init
    assert "intents.md" not in init
    assert "形成`初始化方案`" in init
    assert "再次显式调用 `$mdf init`" in init
    assert "context/research/" in init
    assert "context/requirements/" in init
    assert "$mdf doc derive" in init
    assert "## 1. 入口检查" in init
    assert "## 2. 盘点与归类" in init
    assert "## 5. 续办" in init
    assert "没有未说明的遗留文件" in init
    assert "README 只作导航" not in init
    for root_document in (
        "`README.md`",
        "`PROJECT.md`",
        "`AGENTS.md`",
        "`GLOSSARY.md`",
    ):
        assert root_document in init
    assert "各自符合`根文档职责`" in init
    assert "检查项目原有的全部文档" in init
    assert "符合 CodeWiki 契约的 `docs/repowiki/`" in init
    assert "盘点全部顶层项目项" in init
    assert "顶层允许清单" in init
    assert "仅含 `.gitkeep` 的占位目录按其未来职责迁移" in init
    assert "业务实现目录" in init
    assert "`src/<目录>`" in init
    assert "`tests/<目录>`" in init
    assert "迁移目标已有实际内容时，\n   在同一方案中移除 `.gitkeep`" in init
    assert "不得在未经确认时迁移或删除" in init
    assert "项目原有文档\n   与经确认迁移的顶层项目项" in init
    inventory = init.split("## 2. 盘点与归类", maxsplit=1)[1].split(
        "## 3. 落地初始化方案", maxsplit=1
    )[0]
    assert "不做`事实复核`" in inventory
    assert "`evidence`" not in inventory
    assert "仅在外层 intent 入口检查一次" in common
    assert "不得重复 clean 检查而拒绝修改" in common
    for document in (create, review):
        assert "object-contract.md" in document
        assert "内部 grill intent" in document
        assert "normal_workflows_allowed" in document
        assert "先在 `draft` 状态运行 `targeted validation`" in document
    assert "生成 ID 与规范化文件名" in create
    assert "英文 ASCII kebab-case slug" in create
    assert "closed 或 archive 对象拒绝修改" in review
    assert "closed Proposal/Bug" in archive


def test_jot_intent_preserves_raw_input_until_promotion() -> None:
    jot = intent("jot")

    assert "make-jot-id" in jot
    assert "JOTS.md" in jot
    assert "完整 marker 条目" in jot
    assert "draft 和原 Jot" in jot
    assert "同一个独立 commit" in jot


def test_repository_contract_defines_static_core_terms() -> None:
    skill = skill_dir("mdf")
    contract = (skill / "references" / "repository-contract.md").read_text(
        encoding="utf-8"
    )
    init = intent("init")

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


def test_repository_contract_defines_top_level_layout() -> None:
    skill = skill_dir("mdf")
    contract = (skill / "references" / "repository-contract.md").read_text(
        encoding="utf-8"
    )

    assert "## 顶层布局" in contract
    assert "顶层只保留项目入口" in contract
    assert "业务实现\n应归入 `src/`，测试应归入 `tests/`" in contract
    assert "MDF 不自动迁移或删除顶层项目项" in contract
    assert "顶层允许清单、" in contract
    assert "每项的理由" in contract
    assert "`docs/repowiki/` 存在时" in contract
    assert "不填入`基线`" in contract


def test_contracts_do_not_duplicate_intent_steps() -> None:
    skill = skill_dir("mdf")
    object_contract = (skill / "references" / "object-contract.md").read_text(
        encoding="utf-8"
    )

    assert not (skill / "references" / "intents.md").exists()
    assert "$mdf " not in object_contract
    assert "release-closeout" not in object_contract
    assert "finish 时" not in object_contract


def test_audit_is_reused_without_delivery_logic() -> None:
    audit = intent("audit")
    init = intent("init")
    finish = intent("finish")

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
    start = intent("start")
    finish = intent("finish")

    assert "master" in start and "develop" in start
    assert "推送到 origin 并设置 upstream" in start
    assert "no-ff 合并到 develop" in finish
    assert "no-ff 合并到" in finish and "master" in finish
    assert "原子 push" in finish
    assert "v<semver>" in finish


def test_codewiki_intents_use_a_managed_mcp_wiki_contract() -> None:
    skill = skill_dir("mdf")
    contract = (skill / "references" / "codewiki-contract.md").read_text(
        encoding="utf-8"
    )
    generate = intent("codewiki-generate")
    update = intent("codewiki-update")

    assert "docs/repowiki/" in contract
    assert "metadata.json" in contract
    assert "module_tree.json" in contract
    assert "first_module_tree.json" in contract
    assert "mdf-codewiki: managed" in contract
    assert "provider" in contract and "API key" in contract
    assert "CodeWiki CLI" in contract
    assert "hacks.md" in contract
    assert "偏离同类功能的普通路径" in contract
    assert "V2" not in contract
    assert "analyze_repo" in generate
    assert "save_module_tree" in generate
    assert "close_session" in generate
    assert "待确认" in generate
    assert "$mdf codewiki update" in generate
    assert "no_changes: true" in update
    assert "不调用 `analyze_repo`" in update
    assert "$mdf codewiki generate" in update
    assert "MCP-only" in update
    assert "在 `overview.md` 加入链接" in update
    assert "V2" not in generate and "V2" not in update
