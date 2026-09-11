"""MDF 对象 ID 与文件名测试。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403


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
