"""发布后在同一 release 分支合回 target，final tag 保持固定。"""
from mdf_test_support import *  # noqa: F403
from support_github_flow import commit, publish_release, error_of
from support_pull import squash_pending
from test_publish_stage import release


def test_release_integrates_main_in_same_worktree(python_exe, tmp_path, monkeypatch):
    repo, remote, platform, work = release(python_exe, tmp_path, monkeypatch)
    (work / "src/release.py").write_text("release_change = True\n")
    commit(work)
    published = publish_release(python_exe, work)
    (repo / "src/service.py").write_text("main_change = True\n")
    commit(repo)
    git(repo, "push", "origin", "main")
    blocked = error_of(mdf(python_exe, "pr", "--repo", str(work)))
    assert blocked["error"] == "integration_required"
    assert git(work, "branch", "--show-current").stdout.strip() == "release/1.3.0"
    pending = payload(mdf(python_exe, "incremental-integration", "--repo", str(work)))
    assert not pending["completed"] and not pending["incr_consolidate"]
    assert pending["plan"]["verify"]["action"] == "smart"
    assert not git(repo, "branch", "--list", "codex/integrate/*").stdout.strip()
    report = "changes/unreleased/1.3.0/incremental-integration-verification-report.json"
    payload(mdf(python_exe, "verify", "--repo", str(work), "--scope", "smart", "--paths", "src/service.py",
                "--report-file", report))
    commit(work)
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    payload(mdf(python_exe, "incremental-integration", "--repo", str(work), "--complete", "--reviewed-head", head,
                "--summary", "本轮 incr-cr、verify smart 和 incr-fa 已通过"))
    context = payload(mdf(python_exe, "review-context", "--repo", str(work), "--source", "release/1.3.0",
                          "--head", "HEAD", "--policy-ref", "origin/main"))["result"]
    assert context["kind"] == "release" and context["delivery_base"] == published
    squash_pending(work)
    payload(mdf(python_exe, "pr", "--repo", str(work)))
    platform.merge(1, tmp_path)
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == published
