from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

from .constants import ALL_MARKDOWN_LINK_RE
from .errors import Finding, add_finding
from .paths import path_stays_in_repo, relative


def managed_markdown(repo: Path) -> Iterable[Path]:
    roots = (
        repo / "PROJECT.md",
        repo / "GLOSSARY.md",
        repo / "CHANGELOG.md",
        repo / "docs",
        repo / "requirements",
        repo / "bugs",
        repo / "changes",
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
                for path in root.rglob("*.md")
                if path.is_file()
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


def validate_links(repo: Path, findings: list[Finding]) -> None:
    for path in managed_markdown(repo):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for raw in ALL_MARKDOWN_LINK_RE.findall(text):
            target = split_link_target(raw)
            if not target:
                if raw and not raw.strip():
                    add_finding(
                        findings,
                        "link.broken",
                        f"Broken local link: {raw}",
                        relative(repo, path),
                    )
                continue
            if target.startswith(("http://", "https://", "mailto:", "data:")):
                continue
            candidate = (
                repo / target.lstrip("/")
                if target.startswith("/")
                else path.parent / target
            )
            resolved = candidate.resolve()
            try:
                resolved.relative_to(repo)
            except ValueError:
                add_finding(
                    findings,
                    "link.outside_repo",
                    f"Local link escapes the repository: {raw}",
                    relative(repo, path),
                )
                continue
            if not resolved.exists():
                add_finding(
                    findings,
                    "link.broken",
                    f"Broken local link: {raw}",
                    relative(repo, path),
                )
