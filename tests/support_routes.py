"""intent 文档结构检查共用的读取与表格解析。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from types import SimpleNamespace
import re
import shlex
import unicodedata
from conftest import skill_dir


HEADER = "| # | 步骤 | 类型 | 做什么 | 证据 | 通过 → | 失败/缺失 → |"


def workflow(name: str) -> str:
    root = skill_dir("mdf")
    path = root / "SKILL.md" if name == "entry" else root / "references" / f"{name}.md"
    return path.read_text(encoding="utf-8")


def rows(text: str) -> list[list[str]]:
    return [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in text.splitlines()
        if re.match(r"^\| \d+ \|", line)
    ]


def compact(text: str) -> str:
    return "".join(text.split())


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def assert_branch_alignment(block, path):
    pattern = r"^(?P<prefix> +[├└]──── )(?P<condition>.*?) (?P<dash>─+)→ (?P<target>.+)$"
    branches = [
        (line, re.fullmatch(pattern, line))
        for line in block.splitlines() if re.match(r" +[├└]", line)
    ]
    assert branches and all(match for _, match in branches), path
    conditions, arrows, targets = set(), set(), set()
    longest = max(display_width(match["condition"]) for _, match in branches)
    has_main = bool(re.search(r"^\s*▼", block, re.MULTILINE))
    for index, (line, match) in enumerate(branches):
        conditions.add(display_width(line[:match.start("condition")]))
        arrows.add(display_width(line[:line.index("→")]))
        targets.add(display_width(line[:match.start("target")]))
        assert len(match["dash"]) == 4 + longest - display_width(match["condition"]), path
        corner = "└" if index == len(branches) - 1 and not has_main else "├"
        assert match["prefix"].lstrip().startswith(corner), path
    assert len(conditions) == len(arrows) == len(targets) == 1, path
