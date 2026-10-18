"""短 ID 与 PRP 编号的格式。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


_ID_LETTERS = set("ABCDEFGHJKLMNPQRSTUVWXYZ")


_ID_DIGITS = set("23456789")


def test_new_short_id_includes_a_letter_and_a_digit():
    load_core_module()
    from mdf_core.foundation.constants import OBJECT_ID_RE
    from mdf_core.foundation.textutil import new_short_id

    for _ in range(200):
        value = new_short_id()
        chars = set(value)
        assert chars <= _ID_LETTERS | _ID_DIGITS
        assert chars & _ID_LETTERS
        assert chars & _ID_DIGITS
        assert OBJECT_ID_RE.fullmatch(f"bug-{value}")


def test_format_prp_id_uses_three_digits_until_1000():
    load_core_module()
    from mdf_core.foundation.constants import PRP_ID_RE
    from mdf_core.foundation.textutil import format_prp_id

    assert format_prp_id(1) == "prp-001"
    assert format_prp_id(99) == "prp-099"
    assert format_prp_id(100) == "prp-100"
    assert format_prp_id(999) == "prp-999"
    assert format_prp_id(1000) == "prp-1000"
    assert format_prp_id(1001) == "prp-1001"
    for value in ("prp-001", "prp-099", "prp-100", "prp-999", "prp-1000"):
        assert PRP_ID_RE.fullmatch(value)
    for value in (
        "prp-000",
        "prp-01",
        "prp-1",
        "prp-01000",
        "prp-AB23",
        "prp-ABCD",
    ):
        assert PRP_ID_RE.fullmatch(value) is None
