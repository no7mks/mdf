"""Adhoc Change 可与普通交付一起进入后续 release。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import commit


def test_release_archives_adhoc_child_and_keeps_its_kind(python_exe, tmp_path):
    repo = prepare_release_closeout_repo(tmp_path)
    source = repo / "changes/unreleased/service-health/CHANGE.md"
    root = repo / "changes/unreleased/update-docs"
    root.mkdir()
    text = source.read_text().replace("change_kind: feature", "change_kind: adhoc")
    text = text.replace("source_branch: feature/service-health", "source_branch: adhoc/update-docs")
    text = text.replace("proposals: [prp-001]", "proposals: []").replace("fixed: [bug-CD34]", "fixed: []")
    (root / "CHANGE.md").write_text(text)
    commit(repo)
    seed_verify_branch(python_exe, repo)
    payload(mdf(python_exe, "release-closeout", "--repo", str(repo), "--release-date", "2026-10-15"))
    archived = repo / "changes/1.3.0/update-docs/CHANGE.md"
    assert archived.is_file() and "change_kind: adhoc" in archived.read_text()
    assert "source_branch: adhoc/update-docs" in archived.read_text()
    assert "update-docs" in (repo / "changes/1.3.0/CHANGE.md").read_text()
    assert not root.exists()
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full"))
