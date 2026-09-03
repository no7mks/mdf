"""Skill、脚本和测试的文件规模检查。"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from pathlib import Path

from _support import REPO_ROOT


MAX_LINE_WIDTH = 120
MAX_FILE_LINES = 500
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
        (number, display_width(line))
        for number, line in enumerate(lines, start=1)
        if len(line) > MAX_LINE_WIDTH
    ]
    return len(lines), widths


def display_width(text: str) -> int:
    """返回显示宽度；全角和宽字符（包括中文）按两个字符计。"""
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1
               for char in text)


def has_split_exception(path: Path) -> bool:
    """检查文件开头是否说明了超过行数上限仍不拆分的理由。"""
    header = "\n".join(
        path.read_text(encoding="utf-8").splitlines()[:20]
    )
    return "不拆分" in header and any(
        word in header for word in ("理由", "原因", "因为")
    )


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
        over_line_limit = (
            line_count > MAX_FILE_LINES and not has_split_exception(path)
        )
        if over_line_limit or widths:
            failures.append(describe(path, line_count, widths))
    assert not failures, "File limits exceeded:\n" + "\n".join(failures)


def test_display_width_counts_chinese_as_two_characters():
    assert display_width("MDF 中文") == 8
