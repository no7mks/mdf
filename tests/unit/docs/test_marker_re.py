"""模板占位符正则只匹配 MDF 槽位。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_marker_re_matches_mdf_slots_not_product_macros():
    load_core_module()
    from mdf_core.foundation.constants import MARKER_RE

    for text in (
        "{{MDF_EVIDENCE_PATH}}",
        "{{MDF_TITLE}}",
        "{{MDF_YYYY_MM_DD}}",
        "TODO: fill this",
        "prefix TODO",
        "TODO",
    ):
        assert MARKER_RE.search(text), text
    for text in (
        "{{EVIDENCE_PATH}}",
        "{{TITLE}}",
        "{{API_KEY}}",
        "{{char}}",
        "{{user}}",
        "{{ user }}",
        "`{{char}}`",
        "```\n{{char}}\n```",
        "{{#if}}{{/if}}",
        "{{.Name}}",
        "{{ FOO }}",
        "{{FOO-BAR}}",
        "{{foo_bar}}",
        "{{MDF_}}",
        "{{}}",
        "TODOLIST",
    ):
        assert MARKER_RE.search(text) is None, text
