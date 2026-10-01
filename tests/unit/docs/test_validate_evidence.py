"""evidence 仅为 path 列表。"""
from mdf_test_support import *  # noqa: F403


def test_frontmatter_evidence_accepts_paths_only():
    load_core_module()
    from mdf_core.validate_evidence import frontmatter_evidence

    assert frontmatter_evidence({"evidence": ["src/a.py", "src/b.py"]}) == [
        "src/a.py",
        "src/b.py",
    ]
    assert frontmatter_evidence(
        {"evidence": [{"path": "src/a.py", "verification": "ignored"}]}
    ) == ["src/a.py"]
    assert frontmatter_evidence(
        {"evidence": {"paths": ["src/a.py"], "verification": "ignored"}}
    ) == ["src/a.py"]
    assert frontmatter_evidence({}) == []
