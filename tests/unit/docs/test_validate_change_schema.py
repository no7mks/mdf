"""子 Change source_branch schema：feature/bugfix 对齐与 develop 直合。"""
from __future__ import annotations

from mdf_test_support import *  # noqa: F403

CHANGE_BODY = (
    "## 结果\n\n已完成。\n\n"
    "## 已更新的当前文档\n\n- docs/user-guide/README.md\n\n"
    "## 已知偏差\n\n无。\n"
)


def _validate():
    load_core_module()
    from mdf_core.inspection.validate_change_schema import validate_change_file

    return validate_change_file


def _write_change(
    path: Path,
    *,
    change_kind: str,
    source_branch: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "---\n"
            f"change_kind: {change_kind}\n"
            f"source_branch: {source_branch}\n"
            "proposals: []\n"
            "fixed: []\n"
            "closed: []\n"
            "deferred: []\n"
            "adrs: []\n"
            "release_notes: none\n"
            "breaking: false\n"
            "evidence:\n"
            "  tests: [tests/test_service.py]\n"
            '  commands: ["python -m pytest"]\n'
            "  artifacts: []\n"
            "---\n\n"
            f"# Change\n\n{CHANGE_BODY}"
        ),
        encoding="utf-8",
    )


def _findings_for(repo: Path, path: Path, *, expected_slug: str) -> list:
    findings: list = []
    _validate()(
        repo, path, findings, expected_slug=expected_slug, root=False
    )
    return findings


def test_develop_sourced_change_accepts_free_slug(tmp_path: Path):
    repo = tmp_path / "repo"
    path = repo / "changes" / "unreleased" / "docs-tweak" / "CHANGE.md"
    _write_change(
        path, change_kind="feature", source_branch="develop"
    )

    findings = _findings_for(repo, path, expected_slug="docs-tweak")

    assert findings == []


def test_develop_sourced_bugfix_kind_is_accepted(tmp_path: Path):
    repo = tmp_path / "repo"
    path = repo / "changes" / "unreleased" / "hotfix-note" / "CHANGE.md"
    _write_change(
        path, change_kind="bugfix", source_branch="develop"
    )

    findings = _findings_for(repo, path, expected_slug="hotfix-note")

    assert findings == []


def test_develop_sourced_rejects_release_kind(tmp_path: Path):
    repo = tmp_path / "repo"
    path = repo / "changes" / "unreleased" / "docs-tweak" / "CHANGE.md"
    _write_change(
        path, change_kind="release", source_branch="develop"
    )

    findings = _findings_for(repo, path, expected_slug="docs-tweak")

    assert any(item.code == "change.kind" for item in findings)


def test_master_source_branch_still_rejected(tmp_path: Path):
    repo = tmp_path / "repo"
    path = repo / "changes" / "unreleased" / "docs-tweak" / "CHANGE.md"
    _write_change(
        path, change_kind="feature", source_branch="master"
    )

    findings = _findings_for(repo, path, expected_slug="docs-tweak")

    assert any(item.code == "change.source_branch" for item in findings)


def test_feature_source_branch_still_requires_slug_match(tmp_path: Path):
    repo = tmp_path / "repo"
    path = repo / "changes" / "unreleased" / "other-slug" / "CHANGE.md"
    _write_change(
        path,
        change_kind="feature",
        source_branch="feature/service-health",
    )

    findings = _findings_for(repo, path, expected_slug="other-slug")

    assert any(item.code == "change.slug" for item in findings)


def test_feature_source_branch_accepts_matching_slug(tmp_path: Path):
    repo = tmp_path / "repo"
    path = (
        repo / "changes" / "unreleased" / "service-health" / "CHANGE.md"
    )
    _write_change(
        path,
        change_kind="feature",
        source_branch="feature/service-health",
    )

    findings = _findings_for(repo, path, expected_slug="service-health")

    assert findings == []


@pytest.mark.parametrize("source_branch,slug", [
    ("develop", "small-correction"),
    ("adhoc/small-correction", "small-correction"),
    ("fix/small-correction", "small-correction"),
    ("scratch", "scratch-unique"),
])
def test_fix_change_accepts_lightweight_sources(tmp_path: Path, source_branch, slug):
    path = tmp_path / "changes/unreleased" / slug / "CHANGE.md"
    _write_change(path, change_kind="fix", source_branch=source_branch)

    assert _findings_for(tmp_path, path, expected_slug=slug) == []


@pytest.mark.parametrize("source_branch,code", [
    ("feature/small-correction", "change.kind"),
    ("bugfix/small-correction", "change.kind"),
    ("master", "change.source_branch"),
])
def test_fix_change_rejects_other_sources(tmp_path: Path, source_branch, code):
    path = tmp_path / "changes/unreleased/small-correction/CHANGE.md"
    _write_change(path, change_kind="fix", source_branch=source_branch)

    findings = _findings_for(tmp_path, path, expected_slug="small-correction")

    assert any(item.code == code for item in findings)


def test_adhoc_fix_allows_independent_slug_but_requires_empty_proposals(tmp_path: Path):
    path = tmp_path / "changes/unreleased/other-slug/CHANGE.md"
    _write_change(path, change_kind="fix", source_branch="adhoc/small-correction")
    path.write_text(path.read_text().replace("proposals: []", "proposals: [prp-0001]"))

    findings = _findings_for(tmp_path, path, expected_slug="other-slug")

    assert "change.proposals" in {item.code for item in findings}
    assert "change.slug" not in {item.code for item in findings}


@pytest.mark.parametrize("source_branch", ["release/1.2.0", "hotfix/1.2.0"])
def test_fix_cannot_be_a_version_root(tmp_path: Path, source_branch):
    path = tmp_path / "changes/1.2.0/CHANGE.md"
    _write_change(path, change_kind="fix", source_branch=source_branch)
    findings = []

    _validate()(tmp_path, path, findings, expected_slug="1.2.0", root=True)

    assert any(item.code == "change.kind" for item in findings)
