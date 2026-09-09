"""验证 Skill 的执行表、路由和副作用边界。"""

from __future__ import annotations

import re
import unicodedata

from conftest import skill_dir

HEADER = "| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |"


def workflow(name: str) -> str:
    root = skill_dir("mdf")
    path = root / "SKILL.md" if name == "entry" else root / "references" / f"{name}.md"
    return path.read_text(encoding="utf-8")


def rows(text: str) -> list[list[str]]:
    return [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in text.splitlines()
        if re.match(r"^\| \d+ \|", line)
    ]


def compact(text: str) -> str:
    return "".join(text.split())


def test_workflows_have_one_complete_table_and_matching_unicode_steps():
    root = skill_dir("mdf")
    documents = [root / "SKILL.md", *sorted((root / "references").glob("*.md"))]
    # 按文件职责识别范围，避免缺少执行表的流程从检查中消失。
    nonprocedural = {
        "repository-contract.md", "object-contract.md", "codewiki-contract.md",
        "delivery-contract.md",
    }
    workflows = [p for p in documents if p.name not in nonprocedural]
    assert len(workflows) == 27
    assert not (root / "intents").exists()
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        assert text.count(HEADER) == 1, path
        assert text.count("## 工作流（唯一执行契约）") == 1, path
        assert "```mermaid" not in text, path
        assert not re.search(r"^\d+\. \*\*", text, re.MULTILINE), path
        table = rows(text)
        numbers = [str(i) for i in range(1, len(table) + 1)]
        assert [row[0] for row in table] == numbers, path
        assert all(len(row) == 7 and all(row) for row in table), path
        assert all(row[2] in {"脚本", "Subagent", "约束"} for row in table), path
        if path.stem == "common":
            assert "## 决策树" not in text
        else:
            diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
            boxes = re.findall(r"^│ (\d+) [A-Za-z][A-Za-z ]+│$", diagram, re.MULTILINE)
            assert boxes == numbers, path
            assert "▼" in diagram, path
            assert "┌" in diagram and "└" in diagram, path
            assert "+---" not in diagram and "---->" not in diagram, path
            assert "├──── " in diagram, path
            # 每个编号步骤都必须有分支，不能只画成功路径。
            blocks = re.split(r"^│ \d+ [A-Za-z][A-Za-z ]+│$", diagram,
                              flags=re.MULTILINE)[1:]
            assert all("├──── " in block for block in blocks), path
        for target in re.findall(r"\]\(#([^)]*)\)", text):
            assert f'<a id="{target}"></a>' in text, (path, target)
        for target in re.findall(r"references/[a-z-]+\.md", text):
            assert (root / target).is_file(), (path, target)
        assert all(
            sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in line) <= 120
            for line in text.splitlines()
        ), path


def test_archive_preview_is_terminal_and_apply_requires_non_preview():
    text = workflow("archive")
    table = rows(text)
    assert table[2][5] == "预览结束；否则 4"
    assert "不进入实际归档" in text
    assert "仅非预览调用授权运行" in text
    diagram = text.split("```text", 1)[1].split("```", 1)[0]
    assert "预览成功 ────→ [展示预览并结束]" in diagram
    assert "非预览" in diagram
    assert "预览成功 ────→ 4" not in diagram


def test_init_accepts_initializing_at_entry_before_readiness_gate():
    text = workflow("init")
    entry = text.split('<a id="s1"></a>', 1)[1].split('<a id="s2"></a>', 1)[0]
    assert "仅允许 initializing finding，或 ready 无 finding" in entry
    assert "用户明确“结束初始化并启用正常工作流”确认" in compact(text)


def test_finish_updates_facts_before_moving_materials():
    text = workflow("finish")
    prepare = text.split('<a id="s3"></a>', 1)[1].split('<a id="s4"></a>', 1)[0]
    assert prepare.index("references/fact-update.md") < prepare.index("move-change")
    assert "delivery check --stage fact-update" in prepare
    assert "- feature：" in prepare
    assert "- bugfix：" in prepare
    assert "- release：" in prepare
    assert "- hotfix：" in prepare
    assert "不要求 `.specs`、唯一 PRP 或 feature gate" in prepare


def test_codewiki_requires_verified_close_and_recoverable_failure():
    update = workflow("codewiki-update")
    generate = workflow("codewiki-generate")
    recovery = workflow("codewiki-recovery")
    contract = workflow("codewiki-contract")
    for text in (update, generate):
        assert "references/codewiki-recovery.md" in text
        assert "关闭前先验收" in text
        assert "不得推进基线" in text
    assert "关闭后Wikidiff为空" in compact(update)
    assert "未写页面时只关闭会话并清理workspace" in compact(contract)
    assert "已部分写入时不调用 `close_session`" in recovery
    assert "不开始另一次增量更新" in recovery
    assert "用户指定的仓外备份位置" in compact(recovery)
    assert "取得针对具体源和目标的明确确认" in recovery
    assert "搬移后不得再调用该 session 的写入或关闭工具" in recovery
    assert "显式`$mdfcodewikigenerate`" in compact(recovery)
    assert "不重新路由回 update" in recovery
    assert "没有hack且无页时跳过写入" in compact(update)


def test_finish_keeps_pending_closeout_on_the_release_path():
    text = workflow("finish")
    table = rows(text)
    assert table[3][5] == "已收口或 feature/bugfix 9；待收口 5"
    assert table[7][5] == "9"
    assert table[8][5] == "10"
    diagram = text.split("```text\n", 1)[1].split("```", 1)[0]
    assert "有写入" not in diagram and "无写入" not in diagram
    assert "preview" not in diagram and "预览" not in diagram
    assert "不提供预览模式" in text
    assert "仅预览或只读时" in text and "说明此入口不支持并停止" in text
    assert "--dry-run" not in text


def test_independent_intents_resolve_the_current_target_before_dispatch():
    entry = workflow("entry")
    dispatch = entry.split('<a id="s3"></a>', 1)[1]
    assert "本次调用" in dispatch
    assert "rev-parse --show-toplevel" in dispatch
    assert "REPO_ROOT" in dispatch
    assert "不使用空值或上次调用的变量" in dispatch
    assert "clarify 不要求 Git 仓库" in dispatch
    assert "init/bootstrap" in dispatch and "普通目录" in dispatch


def test_implementation_handoff_distinguishes_checks_from_remaining_work():
    text = workflow("implement")
    assert text.index("逐项对照 objectives") < text.index("delivery record")
    assert "命令、退出状态、结果及对应验收项" in text
    assert "不要求测试先完成或项目全绿" in text
    assert "不记录通过的 implement gate" in text
    assert "区分已验证结论与未验证项" in text


def test_initialization_and_init_have_explicit_reaudit_routes():
    shared = workflow("initialization")
    assert rows(shared)[6][6] == "事实变化 5；其他保留现场停止"
    assert rows(workflow("init"))[6][6] == "事实变化 6；其他保留现场停止"
    assert "bootstrap 不调用 fact audit" in shared
    assert "用户明确“结束初始化并启用正常工作流”确认" in shared
