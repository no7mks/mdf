"""sync intent 的文档路由与约束。"""
from __future__ import annotations
from support_routes import *  # noqa: F403


def test_sync_pulls_trunks_then_pushes_and_reports_extras():
    text = workflow("sync")
    table = rows(text)
    assert [row[1] for row in table] == [
        "Check root", "Preview branches", "Confirm sync", "Sync trunks", "Report result",
    ]
    assert "sync --repo" in text
    assert "master" in text and "develop" in text and "planning" in text
    assert "先全部 pull，再全部 push" in text
    assert "github-flow 同步 trunk 与两侧共有的 support 分支" in text
    assert "extra_local" in text and "extra_remote" in text
    assert "force-push" in text
    assert "不要求 manifest ready" in text
