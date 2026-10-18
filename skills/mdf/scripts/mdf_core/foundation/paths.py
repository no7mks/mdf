from pathlib import Path
from typing import Any

from mdf_core.foundation.constants import MANAGED_ROOTS
from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.yamlutil import parse_yaml


def manifest_path(repo: Path) -> Path:
    return repo / ".mdf" / "manifest.yaml"


def path_stays_in_repo(repo: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(repo)
    except ValueError:
        return False
    return True


def managed_symlinks(repo: Path) -> list[Path]:
    found: set[Path] = set()
    for name in MANAGED_ROOTS:
        root = repo / name
        if root.is_symlink():
            found.add(root)
            continue
        if root.is_dir() and path_stays_in_repo(repo, root):
            found.update(path for path in root.rglob("*") if path.is_symlink())
    return sorted(found)


def ensure_safe_managed_paths(repo: Path) -> None:
    unsafe = managed_symlinks(repo)
    if unsafe:
        raise MDFError(
            "MDF-managed paths must not be symbolic links",
            code="managed_symlink",
            details={
                "paths": [path.relative_to(repo).as_posix() for path in unsafe]
            },
        )


def load_manifest(repo: Path) -> dict[str, Any]:
    path = manifest_path(repo)
    if not path.is_file():
        raise MDFError("Missing .mdf/manifest.yaml", code="not_initialized")
    if path.is_symlink() or not path_stays_in_repo(repo, path):
        raise MDFError(
            "MDF manifest must be a regular repository file",
            code="managed_symlink",
        )
    return parse_yaml(path.read_text(encoding="utf-8"))


def relative(repo: Path, path: Path) -> str:
    return path.resolve().relative_to(repo).as_posix()
