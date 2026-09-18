from pathlib import Path

from .constants import RETIRED_DOC_DIRS
from .errors import Finding, add_finding
from .paths import path_stays_in_repo


def validate_layout(repo: Path, findings: list[Finding]) -> None:
    """docs 布局必须符合当前契约；不属于当前布局的目录由 migrate 收敛。"""
    for raw in RETIRED_DOC_DIRS:
        path = repo / raw
        if path.is_dir() and not path.is_symlink() and path_stays_in_repo(
            repo, path
        ):
            add_finding(
                findings,
                "layout.migrate",
                f"{raw} 不属于当前文档布局；运行 $mdf migrate 收敛",
                raw,
            )
