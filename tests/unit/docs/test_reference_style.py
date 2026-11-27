"""参考页分类闭合与规则边界。"""

from itertools import chain

import pytest

from mdf_test_support import load_core_module

load_core_module()
from mdf_core.inspection.reference_style import classify_lines, document_style


def reference_page(total=460, *, fill="| 参数 | 值 |"):
    rows = ["---", "doc_style: reference", "---"]
    for index in range(total - 3):
        rows.append(f"## 节 {index}" if index % 100 == 0 else fill)
    return "\n".join(rows) + "\n"


def codes(text, role="fact", rel="docs/system/interfaces/topic.md"):
    _, limit, findings = document_style(rel, text, role, 450)
    return limit, {finding.code for finding in findings}


@pytest.mark.parametrize("total", [450, 451, 1200, 1201])
def test_reference_limits_and_shared_role(total):
    assert codes(reference_page(total)) == (1200, set())


@pytest.mark.parametrize("rel", ["README.md", "docs/system/overview.md", "docs/context/adr/x.md", "docs/bugs/x.md"])
def test_reference_role_errors_apply_to_short_pages(rel):
    assert codes("---\ndoc_style: reference\n---\n# 短页\n", "other", rel) == (450, {"doc_style.disallowed_role"})
    assert codes("---\ndoc_style: invalid\n---\n# 短页\n", "other", rel) == (450, {"doc_style.invalid"})


@pytest.mark.parametrize("fill, expected", [
    ("| " + "中" * 121 + " |", {"reference.cell_too_long"}),
    ("| [说明](" + "x" * 300 + ") |", set()),
    ("散文。", {"reference.prose_heavy"}),
])
def test_reference_structure(fill, expected):
    assert codes(reference_page(fill=fill)) == (1200, expected)


@pytest.mark.parametrize("where", ["first", "middle", "last"])
def test_reference_section_spans(where):
    text = reference_page()
    lines = text.splitlines()
    if where == "first":
        lines[3] = lines[103] = "| 表 |"
    elif where == "middle":
        lines[203] = "| 表 |"
    else:
        lines[303] = lines[403] = "| 表 |"
    assert codes("\n".join(lines))[1] == {"reference.section_span"}


def test_fence_comment_heading_table_and_list_classification():
    lines = [
        "## 标题", "````md", "<!-- 忽略", "~~~", "```", "", "```` ",
        "<!-- 注释", "多行 -->可见正文", "<a id=\"anchor\"></a>",
        "可见正文 <!-- 开启", "关闭 -->", "| 表格 |", "- 列表", "  | 列表续行 |",
        "~~~markdown", "## 代码内标题", "~~~", "> 引文",
    ]
    kinds = [kind for kind, _, _ in classify_lines("\n".join(lines))]
    assert kinds == list(chain(
        ["heading"], ["code"] * 4, ["blank", "code", "comment", "prose", "comment",
         "prose", "comment", "table", "list", "list", "code", "code", "code", "prose"],
    ))
    assert len(kinds) == len(lines)


def test_new_scan_reads_updated_frontmatter(tmp_path):
    from mdf_core.inspection.scan_context import RepoScanContext

    path = tmp_path / "topic.md"
    path.write_text("---\ntitle: Before\n---\n")
    scan = RepoScanContext(tmp_path)
    assert scan.frontmatter(path)[0]["title"] == "Before"
    path.write_text("---\ntitle: After\n---\n")
    assert RepoScanContext(tmp_path).frontmatter(path)[0]["title"] == "After"


@pytest.mark.parametrize("body, expected", [
    ("- item\n\n  散文", ["list", "blank", "list"]),
    ("```inline``` 散文\n正文", ["prose", "prose"]),
    ("用 `<!-- jot: marker` 开头。\n## 标题", ["prose", "heading"]),
    ("用 `` `<!--` `` 开头。\n## 标题", ["prose", "heading"]),
])
def test_reference_markdown_boundaries(body, expected):
    assert [kind for kind, _, _ in classify_lines(body)] == expected


@pytest.mark.parametrize("prefix", ["- item\n\n", "```inline``` 散文\n"])
def test_reference_prose_cannot_hide_after_list_or_inline_fence(prefix):
    body = "".join(f"## 节 {i}\n" + prefix + "  散文。\n" * 120 for i in range(4))
    assert "reference.prose_heavy" in codes("---\ndoc_style: reference\n---\n" + body)[1]


def test_reference_inline_comment_marker_preserves_sections():
    assert codes(reference_page(fill="| 用 `<!-- jot: marker` 开头 | 值 |")) == (1200, set())


@pytest.mark.parametrize("body, expected", [
    ("    ```x\n正文\n## 标题", ["code", "prose", "heading"]),
    ("   ```x\n正文\n    ```\n仍在围栏\n   ```\n## 标题",
     ["code", "code", "code", "code", "code", "heading"]),
    ("1. item\n\n   ```text\n   内容\n   ```\n\n   续段",
     ["list", "blank", "code", "code", "code", "blank", "list"]),
])
def test_fence_indentation_boundaries(body, expected):
    assert [kind for kind, _, _ in classify_lines(body)] == expected


@pytest.mark.parametrize("body, expected", [
    ("`a\nb` <!-- c\n## H", ["prose", "prose", "heading"]),
    ("开头 `a\n文字 <!-- b`\n## H", ["prose", "prose", "heading"]),
    ("开头 ``a\n文字 ` <!-- b``\n## H", ["prose", "prose", "heading"]),
    ("`a\nb` <!-- c\n结束 -->\n## H", ["prose", "prose", "comment", "heading"]),
    ("`未闭合\n正文\n## H", ["prose", "prose", "heading"]),
    ("<!-- 未闭合\n## H", ["comment", "comment"]),
])
def test_multiline_code_spans_and_comments(body, expected):
    assert [kind for kind, _, _ in classify_lines(body)] == expected


@pytest.mark.parametrize("body, expected", [
    ("1. a\n\n   b", ["list", "blank", "list"]),
    ("10. a\n\n   b", ["list", "blank", "prose"]),
    ("10. a\n\n    b", ["list", "blank", "list"]),
    ("- a\n\n非列表\n  续行", ["list", "blank", "prose", "prose"]),
    ("10. a\n\n    ```py\n    内容\n    ```\n\n    续段",
     ["list", "blank", "code", "code", "code", "blank", "list"]),
    ("- ```py\n  内容\n  ```\n\n  续段", ["code", "code", "code", "blank", "list"]),
    ("- a\n\n      ```x\n  续段", ["list", "blank", "code", "list"]),
])
def test_list_continuations_and_container_fences(body, expected):
    assert [kind for kind, _, _ in classify_lines(body)] == expected


def test_short_list_continuations_do_not_make_reference_prose_heavy():
    body = "".join(f"## 节 {i}\n\n- 项目\n\n  简短续段。\n\n" + "| 参数 | 值 |\n" * 100 for i in range(5))
    assert codes("---\ndoc_style: reference\n---\n" + body) == (1200, set())


@pytest.mark.parametrize("content", ["  | 参数 | 值 |\n" * 120, "  ```py\n" + "  value = 1\n" * 115 + "  ```\n"])
def test_list_tables_and_code_do_not_consume_prose_budget(content):
    body = "".join(f"## 节 {i}\n\n- 项目\n\n" + content for i in range(4))
    assert codes("---\ndoc_style: reference\n---\n" + body) == (1200, set())


@pytest.mark.parametrize("body, expected", [
    ("10. outer\n    - child\n\n    parent continuation", ["list", "list", "blank", "list"]),
    ("10. outer\n    - child\n\n    ```py\n    value\n    ```\n\n    tail",
     ["list", "list", "blank", "code", "code", "code", "blank", "list"]),
    ("    - example\n\n      still indented code", ["code", "blank", "code"]),
    ("-     sample\n\n  continuation", ["code", "blank", "list"]),
])
def test_nested_list_and_marker_padding(body, expected):
    assert [kind for kind, _, _ in classify_lines(body)] == expected


def test_parent_list_prose_cannot_hide_after_nested_item():
    body = "".join(f"## 节 {i}\n\n10. outer\n    - child\n\n" + "    普通续段。\n" * 110 for i in range(4))
    assert "reference.prose_heavy" in codes("---\ndoc_style: reference\n---\n" + body)[1]


def test_literal_marker_in_continuation_does_not_reset_prose_budget():
    section = "- outer\n\n  continuation starts\n      - literal marker\n" + "  普通续段。\n" * 110
    body = "".join(f"## 节 {i}\n\n" + section for i in range(4))
    assert "reference.prose_heavy" in codes("---\ndoc_style: reference\n---\n" + body)[1]
