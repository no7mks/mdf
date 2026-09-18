"""按加载角色检查文档体积。

角色由仓库相对路径决定；行数为物理行。AGENTS.md 只计 MDF 托管区块。
"""

from pathlib import Path
from typing import Iterable

from .constants import (
    ADR_ROOT,
    ENTRY_DOCUMENTS,
    FACT_ROOTS,
    MDF_BLOCK_END,
    MDF_BLOCK_START,
    SIZE_ADR,
    SIZE_FACT,
    SIZE_PROJECT,
    SIZE_ROUTER,
    SIZE_WORK_ITEM,
)
from .errors import Finding
from .paths import path_stays_in_repo, relative

ROUTER_PATHS = {
    "README.md",
    "AGENTS.md",
    "docs/README.md",
    "docs/user-guide/README.md",
    "docs/system/overview.md",
}
WORK_ITEM_ROOTS = ("docs/proposals/", "docs/bugs/")


def size_role(rel: str) -> tuple[str, int | None, int] | None:
    if rel in ROUTER_PATHS:
        return SIZE_ROUTER
    if rel == "PROJECT.md":
        return SIZE_PROJECT
    parts = rel.split("/")
    if rel.startswith("docs/system/") and len(parts) == 4 and parts[3] == "index.md":
        return SIZE_ROUTER
    if any(rel.startswith(f"{root}/") for root in FACT_ROOTS):
        return SIZE_FACT
    if rel.startswith(f"{ADR_ROOT}/"):
        return SIZE_ADR
    if rel.startswith(WORK_ITEM_ROOTS) or rel == "docs/JOTS.md":
        return SIZE_WORK_ITEM
    return None


def line_count(path: Path, rel: str) -> int:
    text = path.read_text(encoding="utf-8")
    if rel == "AGENTS.md":
        start = text.find(MDF_BLOCK_START)
        end = text.find(MDF_BLOCK_END)
        if start < 0 or end < start:
            return 0
        text = text[start : end + len(MDF_BLOCK_END)]
    return len(text.splitlines())


def sizable_documents(repo: Path) -> list[Path]:
    """全量检查面：根入口文档与 docs/ 下所有带角色的 Markdown。"""
    found: set[Path] = set()
    for raw in ENTRY_DOCUMENTS:
        path = repo / raw
        if path.is_file() and not path.is_symlink():
            found.add(path)
    docs = repo / "docs"
    if docs.is_dir() and not docs.is_symlink():
        found.update(
            path
            for path in docs.rglob("*.md")
            if path.is_file()
            and not path.is_symlink()
            and path_stays_in_repo(repo, path)
        )
    return sorted(
        path for path in found if size_role(relative(repo, path)) is not None
    )


def size_findings(
    repo: Path, paths: Iterable[Path]
) -> tuple[list[Finding], list[Finding]]:
    findings: list[Finding] = []
    warnings: list[Finding] = []
    for path in sorted(set(paths)):
        rel = relative(repo, path)
        role = size_role(rel)
        if role is None or not path.is_file():
            continue
        name, soft, hard = role
        count = line_count(path, rel)
        if count > hard:
            findings.append(
                Finding(
                    "size.hard",
                    f"{name} 文档 {count} 行，超过硬限制 {hard}；须拆页或下沉",
                    rel,
                )
            )
        elif soft is not None and count > soft:
            warnings.append(
                Finding(
                    "size.soft",
                    f"{name} 文档 {count} 行，超过软限制 {soft}；应考虑拆页",
                    rel,
                    "warning",
                )
            )
    return findings, warnings
