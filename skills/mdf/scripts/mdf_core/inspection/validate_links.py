from pathlib import Path
import html
import re
import json
import posixpath
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import unquote

from mdf_core.foundation.constants import ALL_MARKDOWN_LINK_RE
from mdf_core.foundation.errors import Finding, MDFError, add_finding, serialize_findings
from mdf_core.foundation.paths import path_stays_in_repo, relative


EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:", "data:")
HTML_ATTRIBUTE_RE = re.compile(r'''\s+([:\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''')


class HTMLLinks(HTMLParser):
    """只从真实 tag 的 href/src 取链接，保留原字符串中的精确位置。"""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.line_starts = [0, *[match.end() for match in re.finditer("\n", text)]]
        self.spans = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        row, column = self.getpos()
        offset = self.line_starts[row - 1] + column
        for match in HTML_ATTRIBUTE_RE.finditer(self.get_starttag_text()):
            if match.group(1).lower() not in {"href", "src"}:
                continue
            group = next(index for index in (2, 3, 4) if match.group(index) is not None)
            self.spans.append((offset + match.start(group), offset + match.end(group),
                               html.unescape(match.group(group))))


def document_link_spans(path: Path, text: str):
    """返回 href/src 或 Markdown link 的原始位置与解码 target。"""
    if path.suffix == ".html":
        return HTMLLinks(text).spans
    return [(match.start(1), match.end(1), match.group(1))
            for match in ALL_MARKDOWN_LINK_RE.finditer(text)]


def is_external_link(target: str) -> bool:
    return target.startswith(EXTERNAL_LINK_PREFIXES)


def resolve_local_link(source: Path, target: str) -> Path:
    """Resolve a Markdown href relative to the file that contains it.

    A leading `/` is site-root (filesystem-absolute), not the repository root.
    """
    return (source.parent / target).resolve()


def canonical_local_link(
    repo: Path,
    source: Path,
    target: str,
    delivery_root: Path | None = None,
) -> str | None:
    """Fingerprint form of a local href, or None to keep the original raw target.

    Missing files are never treated as inside the delivery directory.
    """
    if not target or is_external_link(target):
        return None
    absolute = resolve_local_link(source, target)
    if not path_stays_in_repo(repo, absolute):
        return None
    relative_path = absolute.relative_to(repo).as_posix()
    if (
        delivery_root is not None
        and absolute.exists()
        and (absolute == delivery_root or delivery_root in absolute.parents)
    ):
        return "@delivery/" + absolute.relative_to(delivery_root).as_posix()
    return relative_path


def managed_markdown(repo: Path) -> Iterable[Path]:
    roots = (
        repo / "PROJECT.md",
        repo / "GLOSSARY.md",
        repo / "CHANGELOG.md",
        repo / "changes",
        repo / "docs",
    )
    found: set[Path] = set()
    for root in roots:
        if root.is_symlink() or not path_stays_in_repo(repo, root):
            continue
        if root.is_file():
            found.add(root)
        elif root.is_dir():
            found.update(
                path
                for path in root.rglob("*")
                if path.is_file()
                and (path.suffix == ".md" or (root.name == "changes" and path.name == "delivery-summary.html"))
                and not path.is_symlink()
                and path_stays_in_repo(repo, path)
            )
    return sorted(found)


def split_link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        parts = target.split(maxsplit=1)
        target = parts[0] if parts else ""
    return unquote(target.split("#", 1)[0].split("?", 1)[0])


def document_link_target(path: Path, raw: str) -> str:
    return split_link_target(f"<{raw}>" if path.suffix == ".html" else raw)


def published_support_head(repo: Path, path: Path) -> str | None:
    """仅逐字匹配已发布 support 归档的文件，才能使用发布树解释历史链接。"""
    from mdf_core.foundation.textutil import stable_semver
    from mdf_core.workspace.merge_policy import git
    from mdf_core.lifecycle.closeout_render import require_tag_content
    parts = path.relative_to(repo).parts
    if len(parts) < 3 or parts[0] != "changes" or stable_semver(parts[1]) is None:
        return None
    identity = repo / "changes" / parts[1] / "delivery.json"
    if not identity.is_file() or identity.is_symlink() or not path_stays_in_repo(repo, identity):
        return None
    try:
        data = json.loads(identity.read_text())
        if (not isinstance(data, dict) or not str(data.get("base_branch", "")).startswith("support/")
                or not str(data.get("branch", "")).startswith("hotfix/") or data.get("version") != parts[1]):
            return None
        head = require_tag_content(repo, parts[1])["head"]
        for candidate in (path, identity):
            rel = candidate.relative_to(repo).as_posix()
            entry = git(repo, "ls-tree", head, "--", f":(literal){rel}").stdout.split()
            if (len(entry) < 3 or entry[0] not in {"100644", "100755"}
                    or git(repo, "hash-object", f"--path={rel}", str(candidate)).stdout.strip() != entry[2]):
                return None
        return head
    except (MDFError, ValueError, OSError):
        return None


def published_link_exists(repo, head, path, target, fragment, check_anchors):
    from mdf_core.workspace.merge_policy import git
    from mdf_core.workspace.changelog_sync import blob_text
    relative_target = posixpath.normpath(posixpath.join(path.relative_to(repo).parent.as_posix(), target))
    if relative_target.startswith(("/", "../")) or relative_target == "..":
        return False
    entry = git(repo, "ls-tree", head, "--", f":(literal){relative_target}").stdout.split()
    if len(entry) < 3 or entry[0] not in {"100644", "100755", "040000"}:
        return False
    suffix = Path(relative_target).suffix
    if check_anchors and fragment and suffix in {".md", ".html"} and entry[1] == "blob":
        return fragment in anchors_from_text(blob_text(repo, head, relative_target), suffix)
    return True


def collect_local_link_findings(
    repo: Path, path: Path, findings: list[Finding], *, targets: set[Path] | None = None,
    check_anchors: bool = False,
) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    published = published_support_head(repo, path)
    for _, _, raw in document_link_spans(path, text):
        target = document_link_target(path, raw)
        href = raw.strip()
        href = href[1:href.index(">") ] if href.startswith("<") and ">" in href else (
            href if path.suffix == ".html" else href.split(maxsplit=1)[0] if href else "")
        fragment = unquote(href.split("#", 1)[1]) if "#" in href else ""
        if not target and fragment:
            target = path.name
        if not target:
            if targets is None and raw and not raw.strip():
                add_finding(
                    findings,
                    "link.broken",
                    f"Broken local link: {raw}",
                    relative(repo, path),
                )
            continue
        if is_external_link(target):
            continue
        resolved = resolve_local_link(path, target)
        if targets is not None and resolved not in targets:
            continue
        if published:
            if not published_link_exists(repo, published, path, target, fragment, check_anchors):
                add_finding(findings, "link.broken", f"Broken published local link: {raw}", relative(repo, path))
            continue
        if not path_stays_in_repo(repo, resolved):
            add_finding(
                findings,
                "link.outside_repo",
                f"Local link escapes the repository: {raw}",
                relative(repo, path),
            )
            continue
        if not resolved.exists() or (check_anchors and fragment and resolved.suffix in {".md", ".html"}
                                     and resolved.is_file() and fragment not in document_anchors(resolved)):
            add_finding(
                findings,
                "link.broken",
                f"Broken local link: {raw}",
                relative(repo, path),
            )


def validate_links(repo: Path, findings: list[Finding]) -> None:
    for path in managed_markdown(repo):
        collect_local_link_findings(repo, path, findings)


def require_existing_local_links(repo: Path, paths: Iterable[Path]) -> None:
    findings: list[Finding] = []
    for path in paths:
        collect_local_link_findings(repo, path, findings)
    if findings:
        raise MDFError(
            "设计材料含无效本地链接",
            code="broken_link",
            details={"findings": serialize_findings(findings)},
        )


def document_anchors(path: Path) -> set[str]:
    """本地 Markdown heading slug 与显式 HTML id/name。"""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return set()
    return anchors_from_text(text, path.suffix)


def anchors_from_text(text: str, suffix: str) -> set[str]:
    if suffix != ".md":
        return set(re.findall(r'(?:id|name)=["\']([^"\']+)["\']', text))
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                lines = lines[index + 1:]
                break
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    fenced = False
    previous = ""
    for line in lines:
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
            previous = ""
            continue
        if fenced:
            continue
        anchors.update(re.findall(r'(?:id|name)=["\']([^"\']+)["\']', line))
        match = re.match(r"^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?$", line)
        setext = bool(previous and re.fullmatch(r" {0,3}(?:=+|-+)\s*", line))
        title = match.group(1) if match else previous if setext else None
        previous = "" if (match or setext or re.match(r"^\s*(?:[-*+]|\d+[.)]|>|\|)", line)) else line.strip()
        if title is None:
            continue
        title = re.sub(r"!?\[([^]]*)\]\([^)]*\)", r"\1", title)
        title = re.sub(r"<[^>]*>", "", title)
        slug = "".join(c for c in html.unescape(title).lower() if c.isalnum() or c in "_ -").replace(" ", "-")
        number = counts.get(slug, 0)
        anchors.add(f"{slug}-{number}" if number else slug)
        counts[slug] = number + 1
    return anchors
