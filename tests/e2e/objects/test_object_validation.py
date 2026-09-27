"""Proposal 与 Bug 的状态、字段、依赖、前缀与唯一性校验。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_manifest_and_work_objects_validate(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert_ok(result)


def test_invalid_object_status_is_rejected(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    bug = repo / "docs/bugs" / BUG_NAME
    replace(bug, "status: open", "status: in_progress")
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert BUG_NAME in result.stdout


def test_ready_object_sections_must_be_filled(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    proposal = repo / "docs/proposals" / PRP_NAME
    replace(
        proposal,
        "## 期望结果\n\n调用方能取得稳定的健康状态。",
        "## 期望结果\n\n",
    )
    replace(
        proposal,
        "### 不包含\n\n- 不提供远程监控。",
        "### 范围外\n\n- 不提供远程监控。",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "object.section_empty" in result.stdout
    assert "proposal.scope" in result.stdout


def test_invalid_depends_on_type_returns_findings_json_without_traceback(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "depends_on: []",
        "depends_on: null",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    data = json.loads(result.stdout)
    assert any(
        finding["code"] == "object.depends_on"
        for finding in data["findings"]
    )


def test_bug_rejects_depends_on_and_requires_severity(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    bug = repo / "docs/bugs" / BUG_NAME
    replace(bug, "severity: major", "depends_on: []")
    init_git(repo)
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    data = json.loads(result.stdout)
    codes = {finding["code"] for finding in data["findings"]}
    assert {"bug.depends_on_forbidden", "bug.severity_required"} <= codes


def test_bug_found_in_accepts_unreleased_sentinel(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


def test_misplaced_object_prefix_is_rejected(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    misplaced = repo / "docs/bugs" / PRP_NAME
    misplaced.write_text(
        (repo / "docs/proposals" / PRP_NAME).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    data = json.loads(result.stdout)
    assert any(
        finding["code"] == "object.filename"
        and finding["path"] == f"docs/bugs/{PRP_NAME}"
        for finding in data["findings"]
    )


def test_validation_rejects_duplicate_id_across_active_and_archive(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    source = repo / "docs/proposals" / PRP_NAME
    archived = repo / "docs/proposals" / "archive" / "1.2" / PRP_NAME
    archived.parent.mkdir(parents=True)
    archived.write_text(
        source.read_text(encoding="utf-8").replace(
            "status: ready\ndepends_on: []",
            (
                "status: released\ndepends_on: []\n"
                ""
                "released_in: 1.2.0"
            ),
        ),
        encoding="utf-8",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "object.id_duplicate" in result.stdout


def test_validation_rejects_id_shaped_filename_slug(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    source = repo / "docs/proposals" / PRP_NAME
    shaped = repo / "docs/proposals" / "prp-003-prp-001.md"
    shaped.write_text(
        source.read_text(encoding="utf-8").replace("prp-001", "prp-003"),
        encoding="utf-8",
    )
    init_git(repo)
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "object.slug_id" in result.stdout


def test_validation_rejects_duplicate_active_slugs(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    bug = repo / "docs/bugs" / "bug-EF56-service-health.md"
    bug.write_text(
        (repo / "docs/bugs" / BUG_NAME).read_text(encoding="utf-8").replace(
            BUG_ID, "bug-EF56"
        ),
        encoding="utf-8",
    )
    init_git(repo)
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "object.slug_duplicate" in result.stdout


def test_validation_allows_archived_slug_reuse(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    source = repo / "docs/proposals" / PRP_NAME
    archived = (
        repo / "docs/proposals" / "archive" / "1.2" / "prp-003-service-health.md"
    )
    archived.parent.mkdir(parents=True)
    archived.write_text(
        source.read_text(encoding="utf-8").replace(
            "id: prp-001", "id: prp-003"
        ).replace(
            "status: ready\ndepends_on: []",
            "status: released\ndepends_on: []\nreleased_in: 1.2.0",
        ),
        encoding="utf-8",
    )
    init_git(repo)
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))
