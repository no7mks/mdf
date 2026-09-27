"""文档结构硬限制的判定。"""
from mdf_test_support import *  # noqa: F403


def codes(text):
    load_core_module()
    from mdf_core.prose import structure_issues
    return [(number, code) for number, code, _ in structure_issues(text)]


def test_structured_text_passes():
    text = (
        "---\ntitle: x\n---\n\n# 标题\n\n一句概述。\n\n"
        "- 项目一\n  续行\n  - 子项\n- 项目二\n\n"
        "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n"
        "```text\n" + "代码行\n" * 20 + "```\n\n"
        "- ⚠️ 易错点\n- ✅ 允许 ❌ 禁止 💡 提示 📌 约束\n"
    )
    assert codes(text) == []


def test_long_prose_block_and_section():
    block = "".join(f"第{index}行说明。\n" for index in range(7))
    assert codes(f"# 节\n\n{block}") == [(3, "prose.block")]
    many = "\n\n".join(["短段落一行。\n短段落二行。"] * 8)
    assert codes(f"# 节\n\n{many}\n") == [(1, "prose.section")]


def test_long_sentence_spans_wrapped_lines_but_links_count_only_text():
    long = "这是一句非常长的说明" * 7
    assert codes(f"{long[:30]}\n{long[30:]}。\n") == [(1, "prose.sentence")]
    link = "见[文档](" + "a/" * 80 + "x.md)。\n"
    assert codes(link) == []


def test_long_list_item_and_disallowed_emoji():
    item = "- 第一行\n  第二行\n  第三行\n  第四行\n  第五行\n"
    assert codes(item) == [(1, "prose.list_item")]
    assert codes("- 🚀 发射\n") == [(1, "prose.emoji")]
