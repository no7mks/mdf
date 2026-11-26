"""Skill、脚本和测试的文件规模检查。"""
from __future__ import annotations
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from _support import REPO_ROOT


MAX_LINE_WIDTH = 180


MAX_FILE_LINES = 500


TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml", ".html"}


TEXT_ROOTS = (".agents", "skills", "tests", "internal", "docs")


ROOT_TEXT_FILES = (
    "AGENTS.md",
    "README.md",
    "PROJECT.md",
    "GLOSSARY.md",
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
        if display_width(line) > MAX_LINE_WIDTH
    ]
    return len(lines), widths


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def describe(path: Path, line_count: int, widths: list[tuple[int, int]]) -> str:
    relative_path = path.relative_to(REPO_ROOT)
    details = [f"lines={line_count}"]
    if widths:
        details.append(
            "widths="
            + ", ".join(f"{number}:{width}" for number, width in widths)
        )
    return f"{relative_path} ({'; '.join(details)})"


def lint_document_style(rel, text, limit):
    from mdf_test_support import load_core_module
    load_core_module()
    from mdf_core.foundation.constants import SIZE_FACT
    from mdf_core.inspection.doc_size import size_role
    from mdf_core.inspection.reference_style import document_style
    role = "fact" if size_role(rel) == SIZE_FACT else "other"
    return document_style(rel, text, role, limit)


def test_file_limits():
    failures: list[str] = []
    for path in checked_files():
        line_count, widths = file_measurement(path)
        limit = 1000 if path.suffix in {".py", ".sh"} else MAX_FILE_LINES
        if path.suffix == ".md":
            rel = path.relative_to(REPO_ROOT).as_posix()
            _, limit, findings = lint_document_style(rel, path.read_text(encoding="utf-8"), limit)
            failures.extend(f"{finding.path}: {finding.code} {finding.message}" for finding in findings)
        over_line_limit = path.suffix != ".html" and line_count > limit
        if over_line_limit or widths:
            failures.append(describe(path, line_count, widths))
    assert not failures, "File limits exceeded:\n" + "\n".join(failures)


def test_line_length_counts_display_width(tmp_path):
    path = tmp_path / "text.md"
    path.write_text("中" * 90 + "\n" + "a" * 180 + "\n", encoding="utf-8")
    assert file_measurement(path) == (2, [])
    path.write_text("中" * 90 + "a" + "\n" + "a" * 181 + "\n", encoding="utf-8")
    assert file_measurement(path) == (2, [(1, 181), (2, 181)])


def test_package_limits():
    from mdf_test_support import load_core_module
    load_core_module()
    from mdf_core.inspection.code_size import package_size_findings
    failures = package_size_findings(REPO_ROOT, checked_files())
    assert not failures, "\n".join(f"{item.path}: {item.message}" for item in failures)
