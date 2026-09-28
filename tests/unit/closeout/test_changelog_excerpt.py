"""发布 tag 使用的 CHANGELOG 本版精简条目。"""
from mdf_test_support import *  # noqa: F403


def excerpt(text: str, version: str) -> str:
    load_core_module()
    from mdf_core.closeout_render import changelog_excerpt

    return changelog_excerpt(text, version)


def test_changelog_excerpt_takes_only_the_named_version():
    text = (
        "# Changelog\n\n"
        "## [1.2.1] - 2026-07-30\n\n"
        "### Fixed\n\n"
        "- 修复超时。\n\n"
        "## [1.2.0] - 2026-01-02\n\n"
        "### Added\n\n"
        "- 旧条目。\n"
    )
    body = excerpt(text, "1.2.1")
    assert body.startswith("## [1.2.1] - 2026-07-30")
    assert "修复超时" in body
    assert "1.2.0" not in body
    assert "旧条目" not in body


def test_changelog_excerpt_rejects_missing_version():
    load_core_module()
    from mdf_core.closeout_render import changelog_excerpt
    from mdf_core.errors import MDFError

    with pytest.raises(MDFError, match="CHANGELOG 缺少 1.2.1"):
        changelog_excerpt("# Changelog\n\n## [1.2.0] - 2026-01-02\n", "1.2.1")


def test_release_tag_message_puts_excerpt_under_subject():
    load_core_module()
    from mdf_core.closeout_render import release_tag_message

    message = release_tag_message("v1.2.1", "## [1.2.1] - 2026-07-30\n\n- 条目。")
    assert message.startswith("chore(release): 发布 v1.2.1\n\n## [1.2.1]")
