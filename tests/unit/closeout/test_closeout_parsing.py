"""closeout 对带引号的 status 与 found_in 的解析。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize(  # noqa: F405
    ("resolution", "closure", "expected_status"),
    [
        (
            "fixed",
            {"id": BUG_ID, "resolution": "fixed", "fixed_in": "1.3.0"},
            "status: closed",
        ),
        (
            "rejected",
            {"id": BUG_ID, "resolution": "wont-fix"},
            'status: "rejected" # pending verification',
        ),
        (
            "deferred",
            {"id": BUG_ID, "resolution": "deferred"},
            'status: "open" # pending verification',
        ),
    ],
)
def test_closeout_uses_parsed_quoted_status_and_found_in(
    resolution: str,
    closure: dict[str, str],
    expected_status: str,
):
    core = load_core_module()  # noqa: F405
    status = (
        "rejected" if resolution == "rejected" else "open" if resolution == "deferred" else "fixed"
    )
    reject_reason = "reject-reason: wont-fix\n" if status == "rejected" else ""
    text = (
        "---\n"
        f"id: {BUG_ID}\n"  # noqa: F405
        "type: bug\n"
        f'status: "{status}" # pending verification\n'
        + reject_reason
        + "severity: major\n"
        + "found_in: 'unreleased' # current line\n"
        + "---\n\n# Bug\n"
    )

    updated = core.close_object_text(
        text,
        kind="bug",
        closure=closure,
        version="1.3.0",
    )

    assert resolution in {"fixed", "rejected", "deferred"}
    assert expected_status in updated
    assert "found_in: 1.3.0" in updated
    assert "unreleased" not in updated
