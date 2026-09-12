"""Mars Development Flow 的确定性协议与事务测试。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403


def test_make_id_bug_uses_the_type_specific_format_and_normalized_slug(
    python_exe: str,
):
    data = payload(
        mdf(python_exe, "make-id", "--type", "bug", "--slug", "  Audit Ready 42!  ")
    )
    assert BUG_ID_RE.fullmatch(data["id"])
    assert data["id"].startswith("bug-")
    assert data["filename"] == f"{data['id']}-audit-ready-42.md"


def test_make_id_proposal_uses_sequential_id_and_normalized_slug(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    data = payload(
        mdf(
            python_exe,
            "make-id",
            "--type",
            "proposal",
            "--repo",
            str(repo),
            "--slug",
            "  Audit Ready 42!  ",
        )
    )
    assert data["id"] == "prp-002"
    assert data["filename"] == "prp-002-audit-ready-42.md"


def test_new_id_alias_no_longer_exists(python_exe: str):
    cli = skill_dir("mdf") / "scripts" / "mdf.py"
    result = run(
        [python_exe, str(cli), "new-id", "--type", "bug", "--slug", "x"]
    )
    assert result.returncode != 0


@pytest.mark.parametrize(
    "version",
    [
        "1.2",
        "version-1.2.3",
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2.3-rc.1",
        "1.2.3+build",
        "0.0.0-unreleased",
    ],
)
def test_release_versions_are_strict_stable_semver(
    python_exe: str, version: str
):
    result = mdf(
        python_exe,
        "semver-check",
        "--previous",
        "1.2.2",
        "--candidate",
        version,
        "--categories",
        "Fixed",
    )
    assert result.returncode != 0
    assert "invalid_semver" in result.stderr


@pytest.mark.parametrize(
    ("previous", "candidate", "categories", "breaking", "expected_ok"),
    [
        ("1.2.3", "1.2.4", "Fixed", False, True),
        ("1.2.3", "1.2.4", "Added", False, False),
        ("1.2.3", "1.3.0", "Added,Fixed", False, True),
        ("1.2.3", "2.0.0", "Added", False, True),
        ("1.2.3", "1.3.0", "Changed", True, False),
        ("1.2.3", "2.0.0", "Changed", True, True),
        ("1.2.3", "1.3.0", "Removed", False, False),
        ("1.2.3", "2.0.0", "Removed", False, False),
        ("0.2.7", "0.2.8", "Fixed", True, False),
        ("0.2.7", "0.3.0", "Fixed", True, True),
    ],
)
def test_minimum_semver_bump(
    python_exe: str,
    previous: str,
    candidate: str,
    categories: str,
    breaking: bool,
    expected_ok: bool,
):
    args = [
        "semver-check",
        "--previous",
        previous,
        "--candidate",
        candidate,
        "--categories",
        categories,
    ]
    if breaking:
        args.append("--breaking")
    result = mdf(python_exe, *args)
    assert (result.returncode == 0) is expected_ok, (
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_removed_category_requires_explicit_breaking_flag(python_exe: str):
    rejected = mdf(
        python_exe,
        "semver-check",
        "--previous",
        "1.2.3",
        "--candidate",
        "2.0.0",
        "--categories",
        "Removed",
    )
    assert rejected.returncode != 0
    assert (
        payload(
            mdf(
                python_exe,
                "semver-check",
                "--previous",
                "1.2.3",
                "--candidate",
                "2.0.0",
                "--categories",
                "Removed",
                "--breaking",
            )
        )["breaking_declared"]
        is True
    )


@pytest.mark.parametrize(
    ("branch", "kind", "slug", "version"),
    [
        ("feature/api/user_auth", "feature", "api-user-auth", None),
        ("bugfix/timeout-fix", "bugfix", "timeout-fix", None),
        ("release/1.4.0", "release", None, "1.4.0"),
        ("hotfix/1.4.1", "hotfix", None, "1.4.1"),
    ],
)
def test_gitflow_branch_classification(
    python_exe: str,
    branch: str,
    kind: str,
    slug: str | None,
    version: str | None,
):
    data = payload(mdf(python_exe, "branch", "--name", branch))
    assert data["kind"] == kind
    if slug is not None:
        assert data["slug"] == slug
    if version is not None:
        assert data["version"] == version


@pytest.mark.parametrize(
    "branch",
    [
        "release/1.2",
        "release/1.2.3-rc.1",
        "hotfix/0.0.0-unreleased",
    ],
)
def test_non_delivery_or_invalid_version_branch_is_rejected(
    python_exe: str, branch: str
):
    result = mdf(python_exe, "branch", "--name", branch)
    assert result.returncode != 0
    assert "bad_release_branch" in result.stderr


@pytest.mark.parametrize("branch", ["main", "develop", "feature/"])
def test_non_delivery_branch_is_classified_as_unsupported(
    python_exe: str, branch: str
):
    data = payload(mdf(python_exe, "branch", "--name", branch))
    assert data["supported"] is False
    assert data["kind"] == "unsupported"


def test_branch_reads_current_git_branch(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "checkout", "-b", "bugfix/unreleased-timeout")

    data = payload(mdf(python_exe, "branch", "--repo", str(repo)))
    assert data["kind"] == "bugfix"
    assert data["slug"] == "unreleased-timeout"


def test_manifest_and_work_objects_validate(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert_ok(result)


def test_manifest_not_applicable_baseline_requires_reason(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    manifest = repo / ".mdf" / "manifest.yaml"
    documented = (
        "  operations:\n"
        "    status: documented\n"
        "    path: docs/system/operations/runbook.md"
    )
    not_applicable = (
        "  operations:\n"
        "    status: not_applicable\n"
        "    reason: 该仓库不交付运行时服务"
    )
    replace(manifest, documented, not_applicable)
    (repo / "docs" / "system" / "operations" / "runbook.md").unlink()
    init_git(repo)
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))
    replace(manifest, "    reason: 该仓库不交付运行时服务\n", "")
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0


def test_audit_rejects_manifest_latest_release_that_disagrees_with_changelog(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / ".mdf" / "manifest.yaml",
        'latest_release: "1.2.0"',
        'latest_release: "9.9.9"',
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert result.returncode != 0
    assert "latest_release" in result.stdout
    assert "9.9.9" in result.stdout


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


def test_validation_rejects_local_link_outside_repository(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    index = repo / "docs" / "README.md"
    index.write_text(
        index.read_text(encoding="utf-8") + "\n[Outside](../../outside.md)\n",
        encoding="utf-8",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "link.outside_repo" in result.stdout


def test_validation_rejects_leading_slash_as_site_root(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    overview = repo / "docs" / "system" / "overview.md"
    overview.write_text(
        overview.read_text(encoding="utf-8")
        + "\n[Root](/docs/product/reference/capabilities.md)\n",
        encoding="utf-8",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "link.outside_repo" in result.stdout


def test_validation_rejects_symlink_in_managed_docs(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    (repo / "docs" / "system" / "escape.md").symlink_to(outside)
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    assert "path.symlink" in result.stdout


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
