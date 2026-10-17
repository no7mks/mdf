"""Structural contract tests that run against EVERY skill in the repo.

These are the future-proof part of the suite: because the `skill` fixture is
parametrized over `discover_skills()` (see conftest.py), any newly added skill
directory with a SKILL.md is automatically validated here — no edits needed.

They check the shape of a skill, not its runtime behaviour:
  - SKILL.md exists and has YAML front-matter
  - front-matter has a non-empty `description`
  - a `name`, if present, matches the directory name
  - scripts referenced from SKILL.md actually exist on disk"""
from __future__ import annotations
import re
from pathlib import Path
from _support import REPO_ROOT, Skill


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):\s?(.*)$")


BLOCK_SCALAR_RE = re.compile(r"^[>|][+-]?$")


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Return top-level scalar keys from YAML front-matter, or None if absent.

    Deliberately tiny: it reads single-line `key: value` pairs plus simple
    block scalars (`>` folded, `|` literal), which is all these SKILL.md
    files use for the fields we assert on (name/description).
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    result: dict[str, str] = {}
    lines = match.group(1).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line[0] in (" ", "\t", "#"):
            # skip blanks, comments and nested (indented) keys
            continue
        m = KEY_RE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if BLOCK_SCALAR_RE.match(value):
            block: list[str] = []
            while (
                i < len(lines)
                and lines[i].strip()
                and lines[i][0] in (" ", "\t")
            ):
                block.append(lines[i].strip())
                i += 1
            joiner = "\n" if value.startswith("|") else " "
            value = joiner.join(block)
        result[key] = value.strip('"').strip("'")
    return result


def test_skill_md_exists(skill: Skill):
    assert skill.skill_md.is_file(), f"{skill.name} is missing SKILL.md"


def test_frontmatter_present(skill: Skill):
    fm = parse_frontmatter(skill.skill_md.read_text(encoding="utf-8"))
    assert fm is not None, (
        f"{skill.name}/SKILL.md has no YAML front-matter block"
    )


def test_description_non_empty(skill: Skill):
    fm = parse_frontmatter(skill.skill_md.read_text(encoding="utf-8")) or {}
    description = fm.get("description", "")
    assert description, (
        f"{skill.name}/SKILL.md front-matter needs a description"
    )
    assert len(description) >= 10, (
        f"{skill.name} description looks too short to be useful"
    )


def test_name_matches_directory(skill: Skill):
    """If a `name` field is present it must match the directory name."""
    fm = parse_frontmatter(skill.skill_md.read_text(encoding="utf-8")) or {}
    name = fm.get("name")
    assert name is not None, (
        f"{skill.name}/SKILL.md must declare an explicit name"
    )
    assert name == skill.name, (
        f"{skill.name}/SKILL.md declares name={name!r}, expected {skill.name!r}"
    )


INVOCATION_RE = re.compile(r"python[0-9]?\s+(scripts/[\w./-]+\.py)")


def test_invoked_scripts_exist(skill: Skill):
    """Every `python scripts/...py` invoked in SKILL.md must exist on disk.

    Catches docs that drift away from the code they describe.
    """
    text = skill.skill_md.read_text(encoding="utf-8")
    referenced = sorted(set(INVOCATION_RE.findall(text)))
    missing = [ref for ref in referenced if not (skill.path / ref).is_file()]
    assert not missing, (
        f"{skill.name}/SKILL.md invokes missing scripts: {missing}"
    )


MDF_LINE_LIMIT = 500


MDF_TEXT_GLOBS = (
    "SKILL.md",
    "references/*.md",
    "scripts/**/*.py",
)


def test_mdf_skill_files_respect_line_limit():
    """MDF skill keeps checked text files below the hard line cap."""
    skill = Skill(
        name="mdf",
        path=REPO_ROOT / "skills" / "mdf",
        skill_md=REPO_ROOT / "skills" / "mdf" / "SKILL.md",
    )
    offenders: list[str] = []
    for pattern in MDF_TEXT_GLOBS:
        for path in sorted(skill.path.glob(pattern)):
            if not path.is_file():
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            limit = 1000 if path.suffix == ".py" else MDF_LINE_LIMIT
            if len(lines) > limit:
                offenders.append(f"{path.relative_to(skill.path)}:{len(lines)} (limit={limit})")
    assert not offenders, (
        f"{skill.name} files exceed {MDF_LINE_LIMIT} lines: {offenders}"
    )
