"""MDF 对象 ID 与文件名测试。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403

_ID_LETTERS = set("ABCDEFGHJKLMNPQRSTUVWXYZ")
_ID_DIGITS = set("23456789")


def test_make_id_requires_an_ascii_slug(
    python_exe: str,
):
    result = mdf(python_exe, "make-id", "--type", "proposal")

    assert result.returncode != 0
    assert "--slug" in result.stderr


def test_make_id_rejects_object_id_slug(python_exe: str):
    result = mdf(
        python_exe, "make-id", "--type", "proposal", "--slug", "prp-AB23"
    )
    assert result.returncode != 0
    assert "slug_is_id" in result.stderr


def test_new_short_id_includes_a_letter_and_a_digit():
    load_core_module()
    from mdf_core.constants import OBJECT_ID_RE
    from mdf_core.textutil import new_short_id

    for _ in range(200):
        value = new_short_id()
        chars = set(value)
        assert chars <= _ID_LETTERS | _ID_DIGITS
        assert chars & _ID_LETTERS
        assert chars & _ID_DIGITS
        assert OBJECT_ID_RE.fullmatch(f"prp-{value}")


def test_make_id_output_includes_a_letter_and_a_digit(python_exe: str):
    data = payload(
        mdf(python_exe, "make-id", "--type", "proposal", "--slug", "mixed-id")
    )
    suffix = data["id"].split("-", 1)[1]
    chars = set(suffix)
    assert PRP_ID_RE.fullmatch(data["id"])
    assert chars & _ID_LETTERS
    assert chars & _ID_DIGITS


def test_id_validation_still_accepts_homogeneous_suffixes(
    python_exe: str, tmp_path: Path
):
    load_core_module()
    from mdf_core.constants import JOT_ID_RE, OBJECT_ID_RE

    assert OBJECT_ID_RE.fullmatch("prp-ABCD")
    assert OBJECT_ID_RE.fullmatch("bug-2345")
    assert JOT_ID_RE.fullmatch("jot-AAAA")
    assert JOT_ID_RE.fullmatch("jot-2222")

    repo = copy_fixture(tmp_path)
    proposal = (repo / "docs/proposals" / PRP_NAME).read_text()
    (repo / "docs/proposals" / "prp-ABCD-letters.md").write_text(
        proposal.replace("prp-AB23", "prp-ABCD")
    )
    bug = (repo / "docs/bugs" / BUG_NAME).read_text()
    (repo / "docs/bugs" / "bug-2345-digits.md").write_text(
        bug.replace("bug-CD34", "bug-2345")
    )
    init_git(repo)
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))
