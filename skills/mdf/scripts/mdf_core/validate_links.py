from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

from .constants import ALL_MARKDOWN_LINK_RE
from .errors import Finding, MDFError, add_finding, serialize_findings
from .paths import path_stays_in_repo, relative


EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:", "data:")


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


def collect_local_link_findings(
    repo: Path, path: Path, findings: list[Finding]
) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
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
        if is_external_link(target):
            continue
        resolved = resolve_local_link(path, target)
        if not path_stays_in_repo(repo, resolved):
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
