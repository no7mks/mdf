"""联调 stdout 的可读行。"""
from __future__ import annotations

from mdf_test_support import *  # noqa: F403


def core():
    load_core_module()
    from mdf_core.integrate_store import format_channel_entry

    return format_channel_entry


def test_channel_entry_keeps_body_out_of_json():
    format_channel_entry = core()
    text = format_channel_entry(
        "out",
        {
            "at": "2026-09-28 20:49:12 +0800",
            "kind": "send",
            "to": "right",
            "from": {"repo": "left", "branch": "master"},
            "body": "看到超时",
        },
    )
    assert text == (
        "2026-09-28 20:49:12 +0800  发出  left/master -> right  send\n"
        "看到超时\n\n"
    )


def test_channel_entry_formats_bug_request_fields():
    format_channel_entry = core()
    text = format_channel_entry(
        "in",
        {
            "at": "2026-09-28 20:49:12 +0800",
            "kind": "bug-request",
            "to": "right",
            "from": {"repo": "left", "branch": "master"},
            "body": {
                "observed": "超时",
                "expected": "成功",
                "repro": "调用一次",
                "impact": "联调阻断",
            },
        },
    )
    assert "收到  left/master -> right  bug-request" in text
    assert "observed: 超时" in text
    assert "{" not in text


def test_channel_entry_formats_heartbeat_without_json():
    format_channel_entry = core()
    text = format_channel_entry(
        "out",
        {
            "at": "2026-09-28 20:49:12 +0800",
            "kind": "heartbeat",
            "to": "right",
            "from": {"repo": "left", "branch": "master"},
            "body": "",
        },
    )
    assert text.startswith(
        "2026-09-28 20:49:12 +0800  发出  left/master -> right  heartbeat\n"
    )
    assert "{" not in text
