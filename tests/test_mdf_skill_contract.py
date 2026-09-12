"""唯一 MDF Skill 的入口与内部 intent 契约测试。"""

from __future__ import annotations

import re

from conftest import skill_dir


def intent(name: str) -> str:
    text = (skill_dir("mdf") / "references" / f"{name}.md").read_text(
        encoding="utf-8"
    )
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"(?<=[\u4e00-\u9fff，。；：、]) (?=[\u4e00-\u9fff])", "", text)


def test_mdf_is_the_only_public_skill_and_dispatches_commands() -> None:
    skill = skill_dir("mdf")
    entry = (skill / "SKILL.md").read_text(encoding="utf-8")

    assert [path.name for path in skill.parent.iterdir() if path.is_dir()] == [
        "mdf"
    ]
    assert not (skill / "workflows").exists()
    expected_commands = (
        "init",
        "bootstrap",
        "intake",
        "next [--depth N]",
        "codewiki generate",
        "codewiki update",
        "start",
        "jot",
        "jot promote",
        "bug create",
        "prp create",
        "prp review",
        "archive",
        "finish",
        "fact audit",
        "fact update",
        "design", "write-tests", "implement", "converge", "review", "prp split",
        "clarify <议题>",
        "help",
        "help <intent>",
        "upgrade",
    )
    for command in expected_commands:
        assert command in entry
    routes = re.findall(r"[├└]──── (.+?) ─+→ references/[a-z-]+\.md", entry)
    commands = [command for route in routes for command in route.split(" / ")]
    assert len(commands) == len(expected_commands)
    assert set(commands) == set(expected_commands)
    assert "裸 `$mdf`" in entry
    assert "references/intake.md" in entry
    assert "references/next.md" in entry
    assert "references/bug-create.md" in entry
    assert "references/prp-create.md" in entry
    assert (skill / "references" / "intake.md").is_file()
    assert (skill / "references" / "next.md").is_file()
    assert not (skill / "references" / "mvp.md").exists()
    assert "doc derive" not in entry
    assert not (skill / "references" / "doc-derive.md").exists()
    assert "references/prp-review.md" in entry
    assert "references/archive.md" in entry
    assert "references/codewiki-generate.md" in entry
    assert "references/codewiki-update.md" in entry
    assert "references/jot.md" in entry
    assert "references/help.md" in entry
    assert "references/upgrade.md" in entry
    assert (skill / "references" / "help.md").is_file()
    assert (skill / "references" / "upgrade.md").is_file()
    assert "$mdf <intent>" in entry
    assert "mdf.py\" <command>" in entry
    assert "版本化文档与交付流程" in entry
    assert "已确认决策与`当前事实文档`分开" in entry
    assert "可验证的演进记录" in entry


def test_next_blueprint_reports_ready_dependency_graph() -> None:
    text = intent("next")
    assert "主报告仅 ready" in text
    assert "implemented/released" in text
    assert "blocked_by" in text
    assert "prp review" in text
    assert "不创建或拆分" in text
    assert "默认 3" in text
    assert "正整数" in text


def test_init_and_doc_intents_load_internal_contracts() -> None:
    init = intent("init")
    intake = intent("intake")
    create = intent("prp-create")
    review = intent("prp-review")
    archive = intent("archive")
    common = intent("common")

    assert "repository-contract.md" in init
    assert "intents.md" not in init
    assert "形成`初始化方案`" in init
    assert "再次显式调用 `$mdf init`" in init
    assert "docs/context/research/" in init
    assert "docs/context/requirements/" not in init
    assert "$mdf intake" in init
    assert "$mdf bug create" in init and "$mdf prp create" in init
    assert "| 1 | 入口 | 脚本 |" in init
    assert "| 2 | 盘点 | 约束 |" in init
    assert "| 7 | 就绪 | 脚本 |" in init
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
    assert "迁移目标已有实际内容时，在同一方案中移除 `.gitkeep`" in init
    assert "不得在未经确认时迁移或删除" in init
    assert "项目原有文档与经确认迁移的顶层项目项" in init
    inventory = init.split('<a id="s2"></a>', maxsplit=1)[1].split(
        '<a id="s5"></a>', maxsplit=1
    )[0]
    assert "不做`事实复核`" in inventory
    assert "`evidence`" not in inventory
    assert "生成的 Markdown 正文、标题与列表使用简体中文" in common
    assert "须写完整前缀 ID，不得省略前缀或只写序号/短码" in common
    assert "核对简体中文、英文保留范围与完整前缀 ID" in common
    for document in (review,):
        assert "object-contract.md" in document
        assert "内部 clarify intent" in document
        assert "normal_workflows_allowed" in document
        assert "先在 `draft` 状态运行 `targeted validation`" in document
    assert "object-contract.md" in intake
    assert "内部 clarify intent" in intake
    assert "normal_workflows_allowed" in intake
    assert "按已有最大序号加一生成 ID" in intake
    assert "英文 ASCII kebab-case slug" in intake
    assert "一句话、当前聊天上下文或外部文档" in intake
    assert "偏差建 Bug" in intake
    assert "待实现意图建一个或多个 Proposal" in intake
    assert "不得复制、归档或链接到仓库" in intake
    assert "必填事实仍无法确认时停止，不得写入任何对象" in intake
    assert "只有用户明确确认清单才继续" in intake
    assert "implemented/released Proposal ID" in intake
    assert "Proposal 初始状态为 `draft`，Bug 初始状态为 `open`" in intake
    assert "显式调用 `$mdf prp review`" in intake
    assert "外部想法、当前聊天上下文或外部文档必须显式调用" in create
    assert "$mdf intake" in create
    assert "一次不得创建多个对象" in create
    assert "用户手动提供的单个 Proposal 事实" in create
    assert "released/rejected/replaced/implemented 或 archive Proposal 拒绝修改" in review
    assert "released/rejected/replaced Proposal 可归档" in archive


def test_jot_intent_preserves_raw_input_until_promotion() -> None:
    jot = intent("jot")

    assert "make-jot-id" in jot
    assert "docs/JOTS.md" in jot
    assert "完整 marker 条目" in jot
    assert "保留新对象、原 Jot" in jot
    assert "Proposal 写为 `draft`，Bug 写为 `open`" in jot
    assert "Proposal 转为 `ready`；Bug 保持 `open`" in jot
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
    assert "docs/context/requirements/" not in contract
    assert "docs/context/planning/" not in contract


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


def test_object_ids_must_be_cited_with_type_prefix() -> None:
    skill = skill_dir("mdf")
    object_contract = (skill / "references" / "object-contract.md").read_text(
        encoding="utf-8"
    )
    agents = (skill / "assets" / "templates" / "agents-managed-block.md").read_text(
        encoding="utf-8"
    )

    assert "必须写完整 ID" in object_contract
    assert "`prp-001`" in object_contract
    assert "`bug-C4D5`" in object_contract
    assert "`jot-E6F7`" in object_contract
    assert "不得省略类型前缀或只写序号/短码" in object_contract
    assert "`bug-`" in agents and "`prp-`" in agents and "`jot-`" in agents
    assert "不得省略前缀或只写序号/短码" in agents


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
    audit = intent("fact-audit")
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
    assert "`fact audit` 执行`全量审阅`" in init
    assert "这是交付前检查，不是 audit" in finish
    assert "references/fact-update.md" in finish
    assert "release 为全量" in finish


def test_start_and_finish_define_strict_gitflow_operations() -> None:
    start = intent("start")
    finish = intent("finish")

    assert "master" in start and "develop" in start
    assert "不 fetch、不要求 origin、不 push" in start
    assert "内部 clarify intent" in start
    assert "不写目标" in start
    assert "feature 2；其他 3" in start
    assert "no-ff 合并到本地 develop" in finish
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
