"""Jot 草稿本的确定性协议测试。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_make_jot_id_uses_short_unambiguous_characters(python_exe: str):
    data = payload(mdf(python_exe, "make-jot-id"))
    assert data["operation"] == "make-jot-id"
    assert JOT_ID_RE.fullmatch(data["id"])


def test_jots_allow_free_markdown_in_marked_entries(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    identifier = "jot-GH01"
    (repo / "docs/JOTS.md").write_text(
        "# 随手记录\n\n"
        f"<!-- jot: {identifier} -->\n"
        "## Retry feedback\n\n"
        "- 优化失败后的提示。\n\n"
        "### Context\n\n"
        "用户不知道下一步该做什么。\n"
        "<!-- /jot -->\n",
        encoding="utf-8",
    )
    init_git(repo)

    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--level", "strict"))


def test_jots_require_marked_nonempty_entries(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    (repo / "docs/JOTS.md").write_text(
        "# 随手记录\n\nraw text\n", encoding="utf-8"
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo), "--level", "strict")
    assert result.returncode != 0
    assert "jot.format" in result.stdout
