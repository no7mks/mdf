"""release 在集成前发布，以及 final tag 的重试与不可变性。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import write_changelog_release
from support_github_flow import commit, error_of, publish_release
from test_pr_flow import pr_repo


def release(python_exe, tmp_path, monkeypatch):
    repo, remote, platform = pr_repo(tmp_path, monkeypatch, trunk="main")
    started = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "release", "--version", "1.3.0",
                          "--objectives-file", str(write_release_objectives(tmp_path))))
    work = Path(started["worktree"])
    write_changelog_release(work, "1.3.0")
    commit(work)
    return repo, remote, platform, work


def test_publish_precedes_integration_and_retries_without_moving_tag(python_exe, tmp_path, monkeypatch):
    repo, remote, platform, work = release(python_exe, tmp_path, monkeypatch)
    (repo / "later.txt").write_text("后续主线改动\n")
    commit(repo)
    git(repo, "push", "origin", "main")
    main_head = git(remote, "rev-parse", "main").stdout
    objectives = (work / "changes/unreleased/1.3.0/objectives.md").read_text()
    assert objectives.index("catch-up") < objectives.index("consolidate") < objectives.index("publish")
    assert error_of(mdf(python_exe, "publish", "--repo", str(work)))["error"] == "stage_prerequisite"
    head = publish_release(python_exe, work)
    assert platform.pulls == []
    assert git(remote, "rev-parse", "main").stdout == main_head
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == head
    assert run(["git", "cat-file", "-e", f"{head}:later.txt"], cwd=repo).returncode != 0
    refs = git(remote, "show-ref").stdout
    before = git(work, "rev-parse", "HEAD").stdout
    again = payload(mdf(python_exe, "publish", "--repo", str(work)))
    assert again["release_head"] == head
    assert git(work, "rev-parse", "HEAD").stdout == before
    assert git(remote, "show-ref").stdout == refs
    payload(mdf(python_exe, "merge-no-ff", "--repo", str(work), "--commit", "origin/main"))
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == head


def test_closeout_checks_remote_tag_without_republishing(python_exe, tmp_path, monkeypatch):
    repo, remote, platform, work = release(python_exe, tmp_path, monkeypatch)
    publish_release(python_exe, work)
    payload(mdf(python_exe, "pr", "--repo", str(work)))
    platform.merge(1, tmp_path)
    git(remote, "update-ref", "-d", "refs/tags/v1.3.0")
    failed = mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", "release/1.3.0")
    assert error_of(failed)["error"] == "release_not_published"
    assert run(["git", "rev-parse", "--verify", "refs/tags/v1.3.0"], cwd=remote).returncode != 0


def test_publish_resumes_after_push_failure(python_exe, tmp_path, monkeypatch):
    _repo, remote, _platform, work = release(python_exe, tmp_path, monkeypatch)
    hook = remote / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    with pytest.raises(AssertionError, match="命令失败"):
        publish_release(python_exe, work)
    local = git(work, "rev-parse", "v1.3.0").stdout
    text = (work / "changes/unreleased/1.3.0/objectives.md").read_text()
    assert "- [ ] publish" in text
    hook.unlink()
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    assert git(remote, "rev-parse", "v1.3.0").stdout == local
