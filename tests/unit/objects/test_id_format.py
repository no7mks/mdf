"""对象随机 ID 格式与冲突处理。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize("identifier", [
    "prp-001", "prp-099", "prp-999", "prp-10000", "prp-0000", "prp-0101", "prp-01A2", "prp-012A", "prp-99Z9", "prp-9999",
])
def test_prp_format_accepts_current_ids(identifier):
    load_core_module()
    from mdf_core.foundation.constants import OBJECT_FILE_RE, OBJECT_ID_RE, PRP_ID_RE
    from mdf_core.foundation.textutil import is_object_id_slug

    assert PRP_ID_RE.fullmatch(identifier)
    assert OBJECT_ID_RE.fullmatch(identifier)
    for extension in ("md", "html"):
        assert OBJECT_FILE_RE.fullmatch(f"{identifier}-example.{extension}")
    assert is_object_id_slug(identifier.lower())


@pytest.mark.parametrize("body", [
    "000", "01", "00001", "1", "A123", "1A23", "12AB", "12I3", "123O", "12a3", "１２３４",
])
def test_prp_format_rejects_invalid_ids(body):
    load_core_module()
    from mdf_core.foundation.constants import OBJECT_FILE_RE, OBJECT_ID_RE, PRP_ID_RE

    assert PRP_ID_RE.fullmatch(f"prp-{body}") is None
    assert OBJECT_ID_RE.fullmatch(f"prp-{body}") is None
    assert OBJECT_FILE_RE.fullmatch(f"prp-{body}-example.md") is None


def test_prp_generator_retries_two_letters_and_allows_zero_one(monkeypatch):
    load_core_module()
    from mdf_core.foundation import textutil

    choices = iter("AB0A010101")
    monkeypatch.setattr(textutil.secrets, "choice", lambda alphabet: next(choices))
    assert textutil.new_prp_id() == "prp-010A"
    assert textutil.new_prp_id() == "prp-0101"


def test_prp_generator_obeys_format():
    load_core_module()
    from mdf_core.foundation.constants import PRP_ID_RE
    from mdf_core.foundation.textutil import new_prp_id

    for _ in range(200):
        identifier = new_prp_id()
        assert len(identifier) == 8
        assert PRP_ID_RE.fullmatch(identifier)


def test_prp_allocation_avoids_active_archive_and_batch_collisions(tmp_path, monkeypatch):
    load_core_module()
    from mdf_core.documents import proposals

    root = tmp_path / "docs/proposals"
    (root / "archive").mkdir(parents=True)
    (root / "prp-01A2-active.md").touch()
    (root / "archive/prp-012A-archived.html").touch()
    candidates = iter(["prp-01A2", "prp-012A", "prp-0101", "prp-0101", "prp-99Z9"])
    monkeypatch.setattr(proposals, "new_prp_id", lambda: next(candidates))
    assert proposals.new_prp_ids(tmp_path, 2) == ["prp-0101", "prp-99Z9"]


def test_prp_allocation_rejects_exhausted_space(tmp_path):
    load_core_module()
    from mdf_core.documents.proposals import new_prp_ids
    from mdf_core.foundation.errors import MDFError

    with pytest.raises(MDFError, match="PRP ID 空间不足"):
        new_prp_ids(tmp_path, 58001)


@pytest.mark.parametrize("body", ["A01B", "01AB", "0000", "1111"])
def test_bug_and_jot_validation_accept_zero_one(body):
    load_core_module()
    from mdf_core.foundation.constants import JOT_ID_RE, OBJECT_FILE_RE, OBJECT_ID_RE
    from mdf_core.foundation.textutil import is_object_id_slug

    assert OBJECT_ID_RE.fullmatch(f"bug-{body}")
    assert OBJECT_FILE_RE.fullmatch(f"bug-{body}-example.md")
    assert JOT_ID_RE.fullmatch(f"jot-{body}")
    assert is_object_id_slug(f"bug-{body.lower()}")


def test_short_id_generator_can_emit_zero_one(monkeypatch):
    load_core_module()
    from mdf_core.foundation import textutil

    choices = iter("A01B")
    monkeypatch.setattr(textutil.secrets, "choice", lambda alphabet: next(choices))
    assert textutil.new_short_id() == "A01B"


def test_new_short_id_includes_a_letter_and_a_digit():
    load_core_module()
    from mdf_core.foundation.textutil import new_short_id

    letters = set("ABCDEFGHJKLMNPQRSTUVWXYZ")
    digits = set("0123456789")
    for _ in range(200):
        value = new_short_id()
        assert len(value) == 4
        assert set(value) <= letters | digits
        assert set(value) & letters
        assert set(value) & digits
