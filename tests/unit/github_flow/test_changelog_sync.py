"""跨维护线的发布索引不能改写实际发布基线。"""
import json
import pytest
from mdf_core.foundation.errors import MDFError
from mdf_core.inspection.validate_release import validate_release_history
from mdf_core.workspace.changelog_sync import insert_section


def test_patch_index_keeps_later_release_baseline(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [1.3.0]\n\n## [1.2.1]\n\n## [1.2.0]\n")
    for version, previous in [("1.3.0", "1.2.0"), ("1.2.1", "1.2.0")]:
        directory = tmp_path / "changes" / version
        directory.mkdir(parents=True)
        (directory / "CHANGE.md").write_text(f"---\nprevious_version: {previous}\n---\n")
    (tmp_path / "changes/1.2.1/delivery.json").write_text(json.dumps({"base_branch": "support/1.2"}))
    findings = []
    validate_release_history(tmp_path, {"versioning": {"latest_release": "1.3.0"}}, findings)
    assert not findings
    assert "previous_version: 1.2.0" in (tmp_path / "changes/1.3.0/CHANGE.md").read_text()


@pytest.mark.parametrize("previous", ["1.3.0", "2.0.0", "1.1.9", "invalid"])
def test_invalid_baseline_still_fails(tmp_path, previous):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [1.3.0]\n\n## [1.2.0]\n")
    directory = tmp_path / "changes/1.3.0"
    directory.mkdir(parents=True)
    (directory / "CHANGE.md").write_text(f"---\nprevious_version: {previous}\n---\n")
    findings = []
    validate_release_history(tmp_path, {"versioning": {"latest_release": "1.3.0"}}, findings)
    assert any(f.code == "release.previous_chain" for f in findings)


def test_support_record_does_not_advance_trunk_latest(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.1]\n\n## [1.2.0]\n")
    directory = tmp_path / "changes/1.2.1"
    directory.mkdir(parents=True)
    (directory / "CHANGE.md").write_text("---\nprevious_version: 1.2.0\n---\n")
    (directory / "delivery.json").write_text(json.dumps({"base_branch": "support/1.2"}))
    findings = []
    validate_release_history(tmp_path, {"versioning": {"latest_release": "1.2.0"}}, findings)
    assert not findings


def test_insert_old_patch_preserves_new_release_and_is_idempotent():
    old = "# Changelog\n\n## [1.3.0] - 2026-11-20\n\n### Added\n\n- 新功能。\n\n## [1.2.0]\n"
    patch = "## [1.2.1] - 2026-11-21\n\n### Fixed\n\n- 修复。"
    result = insert_section(old, "1.2.1", patch)
    assert result.index("1.3.0") < result.index("1.2.1") < result.index("1.2.0")
    assert insert_section(result, "1.2.1", patch) == result
    with pytest.raises(MDFError, match="不一致"):
        insert_section(result, "1.2.1", patch.replace("修复。", "其他内容。"))


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_insertion_preserves_existing_bytes(newline):
    prefix = "# Changelog\n\n## [1.3.0]\n\n正文  \n\n\n".replace("\n", newline)
    suffix = "## [1.2.0]\n\n历史。\n".replace("\n", newline)
    result = insert_section(prefix + suffix, "1.2.1", "## [1.2.1]\n\n### Fixed\n\n- 修复。")
    assert result.startswith(prefix) and result.endswith(suffix)


@pytest.mark.parametrize("previous", ["none", "1.0.0"])
def test_single_line_cannot_skip_actual_previous_version(tmp_path, previous):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.0]\n\n## [1.1.0]\n\n## [1.0.0]\n")
    directory = tmp_path / "changes/1.2.0"
    directory.mkdir(parents=True)
    (directory / "CHANGE.md").write_text(f"---\nprevious_version: {previous}\n---\n")
    findings = []
    validate_release_history(tmp_path, {"versioning": {"latest_release": "1.2.0"}}, findings)
    assert any(f.code == "release.previous_chain" for f in findings)


def test_crlf_repeat_is_noop():
    original = "# Changelog\r\n\r\n## [1.2.0]\r\n"
    excerpt = "## [1.2.1]\n\n### Fixed\n\n- 修复。"
    updated = insert_section(original, "1.2.1", excerpt)
    assert insert_section(updated, "1.2.1", excerpt) == updated
