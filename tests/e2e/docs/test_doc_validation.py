"""manifest 基线、latest_release 与本地链接的校验。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


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

    result = mdf(python_exe, "validate", "--repo", str(repo), "--level", "strict")
    assert result.returncode != 0
    assert "latest_release" in result.stdout
    assert "9.9.9" in result.stdout


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
        + "\n[Root](/docs/user-guide/README.md)\n",
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


@pytest.mark.parametrize("name", ["logs", "reports", "tmp"])
def test_validation_ignores_symlinks_inside_local_artifacts(python_exe, tmp_path, name):
    from mdf_core.execution.run_logs import ignored_dir

    repo = copy_fixture(tmp_path)
    root = ignored_dir(repo / ".mdf" / name)
    (root / "escape").symlink_to(tmp_path / "outside")
    init_git(repo)

    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["normal_workflows_allowed"] is True
    assert not any(item["code"] == "path.symlink" for item in data["findings"])


@pytest.mark.parametrize("record", [".mdf/manifest.yaml", "CHANGELOG.md"])
def test_release_records_cannot_be_evidence(python_exe, tmp_path, record):
    repo = copy_fixture(tmp_path)
    page = repo / "docs/system/testing/conventions.md"
    replace(page, "  - path: GLOSSARY.md", f"  - path: {record}")
    init_git(repo)
    result = mdf(python_exe, "validate", "--repo", str(repo), "--level", "strict")
    assert "evidence.record" in result.stdout


def test_route_page_does_not_expire_when_its_leaf_changes(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    leaf = repo / "docs/system/testing/conventions.md"
    leaf.write_text(leaf.read_text() + "\n补充一句约定。\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 叶子页晚于路由页更新")
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--level", "strict"))


@pytest.mark.parametrize("name", ["logs", "reports", "tmp"])
def test_local_artifact_directory_symlink_is_nonblocking_warning(python_exe, tmp_path, name):
    import shutil

    repo = copy_fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = repo / ".mdf" / name
    if link.exists():
        shutil.rmtree(link)
    link.symlink_to(outside, target_is_directory=True)
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["normal_workflows_allowed"] is True
    warnings = [item for item in data["findings"] if item["code"] == "path.symlink"]
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"
    assert warnings[0]["path"] == f".mdf/{name}"
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert_ok(result)
    assert payload(result)["ok"] is True
    assert_ok(mdf(python_exe, "archive", "--repo", str(repo), "--epoch", "1.3", "--dry-run"))
    assert_ok(mdf(python_exe, "fact-audit", "--repo", str(repo), "--scope", "full"))
    if name == "logs":
        assert any(outside.glob("*-doctor/meta.json"))
