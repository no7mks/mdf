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
    workflows = [p for p in documents if HEADER in p.read_text(encoding="utf-8")]
    assert len(workflows) == 25
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
    assert "预览成功 ────> [展示预览并结束]" in diagram
    assert "非预览" in diagram
    assert "预览成功 ────> 4" not in diagram


def test_init_accepts_initializing_at_entry_before_readiness_gate():
    text = workflow("init")
    entry = text.split('<a id="s1"></a>', 1)[1].split('<a id="s2"></a>', 1)[0]
    assert "允许且仅允许 `manifest.initializing` finding" in entry
    assert "尚未初始化时允许继续" in entry
    assert "除 `manifest.initializing` 外的其他 finding" in entry
    assert "用户明确“结束初始化并启用正常工作流”确认" in compact(text)


def test_finish_updates_facts_before_moving_materials():
    text = workflow("finish")
    prepare = text.split('<a id="s3"></a>', 1)[1].split('<a id="s4"></a>', 1)[0]
    assert prepare.index("references/fact-update.md") < prepare.index("move-change")
    assert "delivery check --stage fact-update" in prepare
    assert "预览仅列待补材料，不写入" in prepare


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
