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

    result = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
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
