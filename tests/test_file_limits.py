"""Skill、脚本和测试的文件规模检查。"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from pathlib import Path

from _support import REPO_ROOT


SOFT_LINE_WIDTH = 80
HARD_LINE_WIDTH = 120
SOFT_FILE_LINES = 400
HARD_FILE_LINES = 500
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml"}
TEXT_ROOTS = (".agents", "skills", "tests", "internal")
ROOT_TEXT_FILES = (
    "AGENTS.md",
    "README.md",
    "link_skills.sh",
    "redeploy_mdf.sh",
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
        if len(line) > SOFT_LINE_WIDTH
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


def test_file_limits_fail_at_hard_thresholds():
    failures: list[str] = []
    for path in checked_files():
        line_count, widths = file_measurement(path)
        hard_widths = [
            (number, width)
            for number, width in widths
            if width > HARD_LINE_WIDTH
        ]
        if line_count > HARD_FILE_LINES or hard_widths:
            failures.append(describe(path, line_count, hard_widths))
    assert not failures, "Hard file limits exceeded:\n" + "\n".join(failures)


def test_file_limits_warn_at_soft_thresholds():
    warnings_to_report: list[str] = []
    for path in checked_files():
        line_count, widths = file_measurement(path)
        if line_count > SOFT_FILE_LINES or widths:
            warnings_to_report.append(describe(path, line_count, widths))
    if warnings_to_report:
        warnings.warn(
            "Soft file-limit warnings:\n" + "\n".join(warnings_to_report),
            stacklevel=1,
        )
