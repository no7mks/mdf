"""兼容修订不把协议全文算进 rules_sha256。"""
from __future__ import annotations


def test_protocol_text_is_outside_the_rules_fingerprint(monkeypatch) -> None:
    from mdf_core.foundation import constants
    from mdf_core.reviewing.context import rules_fingerprint

    first = rules_fingerprint({"mdf": "协议正文 A", "project": None})
    assert first == rules_fingerprint({"mdf": "协议正文 B", "project": None})
    monkeypatch.setattr(constants, "PROTOCOL_VERSION", constants.PROTOCOL_VERSION + 1)
    assert rules_fingerprint({"mdf": "协议正文 A", "project": None}) != first
