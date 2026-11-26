"""参考页的物理行分类与体裁规则。"""

import re
from collections import Counter

from mdf_core.foundation.errors import Finding, MDFError
from mdf_core.foundation.yamlutil import frontmatter_span, parse_yaml
from mdf_core.inspection.prose import width

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING = re.compile(r"^(#{1,6})\s")
LIST = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+")
ANCHOR = re.compile(r"""\s*<a\s+id=(?:"[^"]+"|'[^']+')\s*>\s*</a>\s*""")
CELL = re.compile(r"(?<!\\)\|")
LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)|!?\[([^\]]*)\]\[[^\]]*\]")


def classify_lines(body):
    """每个物理行只属于一个类别，返回类别、可见文本和标题级别。"""
    fence = None
    in_comment = False
    list_indent = None
    for line in body.splitlines():
        if fence:
            if re.fullmatch(rf"\s*{fence[0]}{{{len(fence)},}}\s*", line):
                fence = None
            yield ("code" if line.strip() else "blank"), line, 0
            continue
        opened = FENCE.match(line) if not in_comment else None
        if opened:
            fence = opened[1]
            list_indent = None
            yield "code", line, 0
            continue

        comment = in_comment
        visible = ""
        while line:
            marker = "-->" if in_comment else "<!--"
            before, found, line = line.partition(marker)
            if not in_comment:
                visible += before
            if not found:
                break
            in_comment = not in_comment
            comment = True
        if not visible.strip():
            yield ("comment" if comment else "blank"), visible, 0
        elif ANCHOR.fullmatch(visible):
            yield "comment", visible, 0
        elif opened := FENCE.match(visible):
            fence = opened[1]
            list_indent = None
            yield "code", visible, 0
        elif item := LIST.match(visible):
            list_indent = len(item[1].expandtabs(4)) + 2
            yield "list", visible, 0
        elif list_indent is not None and len(visible.expandtabs(4)) - len(visible.expandtabs(4).lstrip()) >= list_indent:
            yield "list", visible, 0
        else:
            list_indent = None
            if heading := HEADING.match(visible):
                yield "heading", visible, len(heading[1])
            elif visible.lstrip().startswith("|"):
                yield "table", visible, 0
            else:
                yield "prose", visible, 0


def document_style(rel, text, role, limit):
    """返回实际角色、上限和体裁 findings，由目标仓与本仓 lint 共用。"""
    body_start = 0
    style = "narrative"
    if text.startswith(("---\n", "---\r\n")):
        try:
            start, end, body_start = frontmatter_span(text)
            style = parse_yaml(text[start:end]).get("doc_style", "narrative")
        except MDFError:
            pass
    if style not in ("narrative", "reference"):
        return role, limit, [Finding("doc_style.invalid", "doc_style 须为 narrative 或 reference", rel)]
    if style == "narrative":
        return role, limit, []
    if role != "fact":
        return role, limit, [Finding("doc_style.disallowed_role", "仅事实主题叶允许声明 reference", rel)]
    findings = []
    if len(text.splitlines()) <= 450:
        return role, 1200, findings

    rows = list(classify_lines(text[body_start:]))
    counts = Counter(kind for kind, _, _ in rows)
    content = len(rows) - counts["blank"] - counts["comment"]
    if counts["prose"] > 150 or counts["prose"] * 5 > content * 2:
        findings.append(Finding("reference.prose_heavy", "参考页散文最多 150 行且占正文最多 40%", rel))
    frontmatter_lines = len(text[:body_start].splitlines())
    sections = []
    for index, (kind, line, level) in enumerate(rows):
        if kind == "table":
            display = LINK.sub(lambda match: match[1] if match[1] is not None else match[2], line)
            if any(width(cell.strip().replace(r"\|", "|")) > 240 for cell in CELL.split(display)):
                findings.append(Finding(
                    "reference.cell_too_long", f"第 {frontmatter_lines + index + 1} 行：表格单元格超过 240 显示宽度", rel,
                ))
        if level in (2, 3):
            sections.append(index)
    edges = [0, *sections, len(rows)]
    if sum(level == 2 for _, _, level in rows) < 3 or any(end - start > 150 for start, end in zip(edges, edges[1:])):
        findings.append(Finding("reference.section_span", "参考页须有至少 3 个二级标题，分节跨度最多 150 行", rel))
    return role, 1200, findings
