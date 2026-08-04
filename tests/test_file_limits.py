"""Skill、脚本和测试的文件规模检查。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from _support import REPO_ROOT


MAX_LINE_WIDTH = 80
MAX_FILE_LINES = 400
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml"}
TEXT_ROOTS = (".agents", "skills", "tests", "internal")
ROOT_TEXT_FILES = (
    "AGENTS.md",
    "README.md",
    "PROJECT.md",
    "GLOSSARY.md",
    "mdf-deploy.sh",
)


def checked_files() -> Iterator[Path]:
    for relative_root in TEXT_ROOTS:
        root = REPO_ROOT / relative_root
        if not root.is_dir():
            continue
        yield from (
            path
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.suffix in TEXT_SUFFIXES
        )
    for relative_path in ROOT_TEXT_FILES:
        path = REPO_ROOT / relative_path
        if path.is_file():
            yield path


def file_measurement(path: Path) -> tuple[int, list[tuple[int, int]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    widths = [
        (number, len(line))
        for number, line in enumerate(lines, start=1)
        if len(line) > MAX_LINE_WIDTH
    ]
    return len(lines), widths


def describe(path: Path, line_count: int, widths: list[tuple[int, int]]) -> str:
    relative_path = path.relative_to(REPO_ROOT)
    details = [f"lines={line_count}"]
    if widths:
        details.append(
            "widths="
            + ", ".join(f"{number}:{width}" for number, width in widths)
        )
    return f"{relative_path} ({'; '.join(details)})"


def test_file_limits():
    failures: list[str] = []
    for path in checked_files():
        line_count, widths = file_measurement(path)
        if line_count > MAX_FILE_LINES or widths:
            failures.append(describe(path, line_count, widths))
    assert not failures, "File limits exceeded:\n" + "\n".join(failures)
