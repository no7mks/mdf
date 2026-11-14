"""HTML 交付总结的可见正文与离线模板。"""
import html
import re
from html.parser import HTMLParser
from pathlib import Path

from mdf_core.foundation.errors import MDFError

class DocumentParser(HTMLParser):
    """将 main 的可见正文投影为结构文本，供总结校验使用。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.main_count = 0
        self.active = False
        self.hidden = 0
        self.links = []
        self.headings = []
        self.heading = None
        self.heading_id = None
        self.outline = []
        self.cells = 0
        self.pre = False
        self.suppressed = []
        self.list_depth = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "main":
            self.main_count += 1
            self.active = True
        if not self.active:
            return
        if tag in {"script", "style", "template"} or "hidden" in values:
            self.hidden += 1
            self.suppressed.append(tag)
        if self.hidden:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
            self.heading = []
            self.heading_id = values.get("id") if tag == "h2" else None
        elif tag in {"ul", "ol"}:
            self.list_depth += 1
            if self.list_depth == 1:
                self.parts.append("\n")
        elif tag in {"p", "section", "pre"}:
            self.parts.append("\n\n")
        elif tag == "li":
            raw_indent = values.get("data-indent", "0")
            if not raw_indent.isdigit() or int(raw_indent) > 120:
                raise MDFError("HTML list 缩进必须为 0–120", code="invalid_html")
            indent = int(raw_indent)
            self.parts.append("\n" + " " * indent + values.get("data-marker", "-") + " ")
        elif tag == "a":
            self.parts.append("[")
            self.links.append(values.get("href", ""))
        elif tag == "img":
            self.parts.append(f"![{values.get('alt', '')}]({values.get('src', '')})")
        elif tag == "code":
            if not self.pre:
                self.parts.append("`")
        if tag == "pre":
            self.pre = True
            self.parts.append("```\n")
        if tag == "br":
            self.parts.append("\n")
        elif tag == "tr":
            self.parts.append("\n|")
            self.cells = 0
        elif tag in {"td", "th"}:
            self.cells += 1
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if not self.active:
            return
        if self.hidden:
            if self.suppressed and tag == self.suppressed[-1]:
                self.hidden -= 1
                self.suppressed.pop()
            return
        if re.fullmatch(r"h[1-6]", tag):
            heading = "".join(self.heading or []).strip()
            self.headings.append(heading)
            if self.heading_id:
                self.outline.append((self.heading_id, heading))
            self.heading = None
            self.heading_id = None
            self.parts.append("\n\n")
        elif tag == "a" and self.links:
            target = self.links.pop()
            self.parts.append("](" + (f"<{target}>" if " " in target else target) + ")")
        elif tag == "code":
            if not self.pre:
                self.parts.append("`")
        elif tag == "pre":
            self.pre = False
            self.parts.append("\n```\n\n")
        elif tag in {"td", "th"}:
            self.parts.append(" |")
        elif tag == "thead":
            self.parts.append("\n|" + " --- |" * self.cells)
        elif tag in {"ul", "ol"}:
            self.list_depth -= 1
            if self.list_depth == 0:
                self.parts.append("\n\n")
        elif tag in {"p", "table"}:
            self.parts.append("\n")
        elif tag == "main":
            self.active = False

    def handle_data(self, data):
        if self.active and not self.hidden:
            if self.list_depth and not self.pre and not data.strip():
                return
            if self.list_depth and not self.pre:
                data = re.sub(r"[\r\n]+\s*", " ", data)
            self.parts.append(data)
            if self.heading is not None:
                self.heading.append(data)


def visible_text(text):
    parser = DocumentParser()
    parser.feed(text)
    if parser.main_count != 1:
        raise MDFError("HTML 必须含唯一 main 正文", code="invalid_html")
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip() + "\n"


def render_document(content, title):
    """给交付总结正文套用离线文档模板。"""
    template = Path(__file__).resolve().parents[3] / "assets/templates/document.html"
    parser = DocumentParser()
    parser.feed("<main>" + content + "</main>")
    outline = "\n".join(f'<li><a href="#{html.escape(anchor)}">{html.escape(label)}</a></li>'
                        for anchor, label in parser.outline)
    slots = {"{{MDF_DOCUMENT_TITLE}}": html.escape(title),
             "{{MDF_DOCUMENT_OUTLINE}}": outline, "{{MDF_DOCUMENT_CONTENT}}": content}
    return re.sub(r"\{\{MDF_[A-Z_]+\}\}", lambda match: slots[match.group()], template.read_text())
