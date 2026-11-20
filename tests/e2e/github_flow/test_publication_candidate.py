"""首次发布绑定本轮候选，重试保持同一发布点。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from support_github_flow import error_of
from support_release_flow import prepared_release


def test_existing_ancestor_tag_cannot_replace_current_consolidated_candidate(python_exe, tmp_path, monkeypatch):
    from mdf_core.lifecycle.closeout_render import expected_tag_message
    _repo, remote, work, _platform = prepared_release(python_exe, tmp_path, monkeypatch)
    earlier = git(work, "rev-parse", "HEAD").stdout.strip()
    git(work, "tag", "-a", "v1.3.0", "--cleanup=verbatim", "-m", expected_tag_message(work, "1.3.0", earlier))
    git(work, "push", "origin", "refs/tags/v1.3.0")
    (work / "src/fix.py").write_text("fixed = True\n")
    payload(mdf(python_exe, "verify", "--repo", str(work), "--scope", "smart", "--paths", "src/fix.py",
                "--report-file", "changes/1.3.0/incremental-integration-verification-report.json"))
    commit(work, "fix: 补齐本轮候选修复")
    payload(mdf(python_exe, "consolidate", "--repo", str(work), "--incremental"))
    current = git(work, "rev-parse", "HEAD").stdout.strip()
    failed = mdf(python_exe, "publish", "--repo", str(work))
    assert error_of(failed)["error"] == "tag_conflict"
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == earlier != current
    assert "- [ ] publish" in (work / "changes/1.3.0/objectives.md").read_text()


def test_published_candidate_survives_later_source_commits(python_exe, tmp_path, monkeypatch):
    _repo, remote, work, _platform = prepared_release(python_exe, tmp_path, monkeypatch)
    published = payload(mdf(python_exe, "publish", "--repo", str(work)))
    (work / "src/integration.py").write_text("integrated = True\n")
    commit(work)
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    retried = payload(mdf(python_exe, "publish", "--repo", str(work)))
    assert retried["release_head"] == published["release_head"]
    assert git(work, "rev-parse", "HEAD").stdout.strip() == head
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == published["release_head"]


def test_empty_version_notes_rejected_before_consolidation_writes(python_exe, tmp_path, monkeypatch):
    _, _, work, _ = prepared_release(python_exe, tmp_path, monkeypatch, consolidate=False)
    change = work / "changes/unreleased/service-health/CHANGE.md"
    change.write_text(change.read_text().replace(
        'release_notes:\n  Added:\n    - "交付可验证的服务健康能力"', 'release_notes: none'))
    commit(work)
    before = git(work, "rev-parse", "HEAD").stdout
    failed = mdf(python_exe, "consolidate", "--repo", str(work), "--release-date", "2026-11-20")
    assert error_of(failed)["error"] == "empty_release_notes"
    assert not git(work, "status", "--porcelain").stdout
    assert git(work, "rev-parse", "HEAD").stdout == before
    assert not (work / "changes/1.3.0").exists()
