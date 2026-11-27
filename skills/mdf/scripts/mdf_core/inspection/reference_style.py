"""参考页的物理行分类与体裁规则。"""

import re
from collections import Counter

from mdf_core.foundation.errors import Finding, MDFError
from mdf_core.foundation.yamlutil import frontmatter_span, parse_yaml
from mdf_core.inspection.prose import width

FENCE = re.compile(r"^ {0,3}(?:(`{3,})[^`]*|(~{3,}).*)$")
HEADING = re.compile(r"^(#{1,6})\s")
LIST = re.compile(r"^( *)(?:[-*+]|\d{1,9}[.)])([ \t]+)")
ANCHOR = re.compile(r"""\s*<a\s+id=(?:"[^"]+"|'[^']+')\s*>\s*</a>\s*""")
CELL = re.compile(r"(?<!\\)\|")
LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)|!?\[([^\]]*)\]\[[^\]]*\]")


def _inline_end(lines, index, column, pattern):
    """行内构造可跨普通文本行，但不越过空行或新的 block。"""
    for row in range(index, len(lines)):
        line = lines[row]
        if row > index and (not line.strip() or HEADING.match(line.lstrip())
                            or FENCE.match(line) or LIST.match(line)):
            break
        match = re.search(pattern, line[column:] if row == index else line)
        if match:
            return row, (column if row == index else 0) + match.end()
    return None


def _visible_text(lines, index, in_comment, code_end):
    line = lines[index]
    position = 0
    visible = ""
    comment = in_comment
    while position < len(line):
        if in_comment:
            closing = line.find("-->", position)
            if closing < 0:
                break
            position = closing + 3
            in_comment = False
        elif code_end:
            end = code_end[1] if index == code_end[0] else len(line)
            visible += line[position:end]
            position = end
            if index == code_end[0]:
                code_end = None
        else:
            token = re.search(r"`+|<!--", line[position:])
            if not token:
                visible += line[position:]
                break
            start, end = position + token.start(), position + token.end()
            visible += line[position:start]
            if token[0].startswith("`"):
                code_end = _inline_end(lines, index, end, rf"(?<!`){token[0]}(?!`)")
                visible += token[0]
            elif (not visible.strip() and len(visible.expandtabs(4)) <= 3
                  or _inline_end(lines, index, end, r"-->")):
                in_comment = comment = True
            else:
                visible += token[0]
            position = end
    return visible, comment, in_comment, code_end


def _list_content_indent(line, parent):
    item = LIST.match(line)
    if item is None or not 0 <= len(item[1]) - parent <= 3:
        return None
    padding = len(item[2])
    return item.start(2) + (padding if padding <= 4 else 1)

def _classified_lines(body):
    """附带真实列表项起始标记，供散文预算直接复用分类结果。"""
    fence = None
    fence_indent = 0
    in_comment = False
    list_indent = None
    list_indents = []
    code_end = None
    paragraph = False
    lines = [line.expandtabs(4) for line in body.splitlines()]
    for index, line in enumerate(lines):
        indent = len(line) - len(line.lstrip(" "))
        if fence:
            if line.strip() and indent < fence_indent:
                fence = None
            else:
                if re.fullmatch(rf" {{0,3}}{fence[0]}{{{len(fence)},}}[ \t]*", line[fence_indent:]):
                    fence = None
                yield ("code" if line.strip() else "blank"), line, 0, False
                continue
        item_indent = None
        if not in_comment and not code_end:
            if line.strip():
                while list_indents and indent < list_indents[-1]:
                    list_indents.pop()
            list_indent = list_indents[-1] if list_indents else None
            item_indent = _list_content_indent(line, list_indent or 0)
            if item_indent is not None:
                list_indents.append(item_indent)
                list_indent = item_indent
            content = line[list_indent:] if list_indent is not None else line
            opened = FENCE.match(content)
            if opened:
                fence = opened[1] or opened[2]
                fence_indent = list_indent or 0
                paragraph = False
                yield "code", line, 0, False
                continue
            if (item_indent is not None or not paragraph) and content.startswith("    "):
                yield "code", line, 0, False
                continue

        visible, comment, in_comment, code_end = _visible_text(lines, index, in_comment, code_end)
        if not visible.strip():
            paragraph = False
            yield ("comment" if comment else "blank"), visible, 0, False
        elif ANCHOR.fullmatch(visible):
            paragraph = False
            yield "comment", visible, 0, False
        elif item_indent is not None:
            paragraph = True
            yield "list", visible, 0, True
        elif list_indent is not None and len(visible) - len(visible.lstrip(" ")) >= list_indent:
            paragraph = True
            yield "list", visible, 0, False
        else:
            list_indent = None
            list_indents.clear()
            paragraph = False
            if heading := HEADING.match(visible):
                yield "heading", visible, len(heading[1]), False
            elif visible.lstrip().startswith("|"):
                yield "table", visible, 0, False
            else:
                paragraph = True
                yield "prose", visible, 0, False


def classify_lines(body):
    """每个物理行只属于一个类别，返回类别、可见文本和标题级别。"""
    for kind, line, level, _ in _classified_lines(body):
        yield kind, line, level


def _prose_lines(rows):
    """列表续段保留 list 分类，空行后的普通文字仍计入散文预算。"""
    continuation = False
    total = 0
    for kind, line, _, new_item in rows:
        if kind == "blank":
            continuation = True
        elif kind == "list":
            if new_item:
                continuation = False
            elif continuation and not line.lstrip().startswith("|") and not HEADING.match(line.lstrip()):
                total += 1
        elif kind == "prose":
            total += 1
            continuation = False
        elif kind not in {"code", "comment"}:
            continuation = False
    return total


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

    classified = list(_classified_lines(text[body_start:]))
    rows = [(kind, line, level) for kind, line, level, _ in classified]
    counts = Counter(kind for kind, _, _ in rows)
    content = len(rows) - counts["blank"] - counts["comment"]
    prose = _prose_lines(classified)
    if prose > 150 or prose * 5 > content * 2:
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
