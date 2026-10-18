"""MDF 自身 Markdown 的结构硬限制；未改写的文件记在 prose_baseline.txt，只减不增。"""
from pathlib import Path

from _support import REPO_ROOT
from mdf_test_support import load_core_module

BASELINE = Path(__file__).with_name("prose_baseline.txt")


def documents():
    patterns = ("skills/**/*.md", ".agents/skills/**/*.md", "docs/**/*.md")
    found = {path for pattern in patterns for path in REPO_ROOT.glob(pattern)}
    found |= {REPO_ROOT / name for name in ("README.md", "PROJECT.md", "AGENTS.md", "GLOSSARY.md")}
    return sorted(path for path in found if path.is_file())


def baseline():
    lines = BASELINE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def test_markdown_meets_structure_limits_or_is_in_baseline():
    load_core_module()
    from mdf_core.inspection.prose import structure_issues
    exempt = baseline()
    failing, cleared = [], []
    for path in documents():
        rel = path.relative_to(REPO_ROOT).as_posix()
        issues = structure_issues(path.read_text(encoding="utf-8"))
        if rel in exempt and not issues:
            cleared.append(rel)
        elif rel not in exempt:
            failing += [f"{rel}:{number} {code} {message}" for number, code, message in issues]
    assert not failing, "\n".join(failing)
    assert not cleared, f"已达标，须移出 prose_baseline.txt: {cleared}"
    assert exempt <= {path.relative_to(REPO_ROOT).as_posix() for path in documents()}
