"""远端同名 release 的增量同步、发布并发与冲突续办。"""
from mdf_test_support import *  # noqa: F403
from support_github_flow import commit, error_of
from test_publish_stage import release


def prepared(python_exe, tmp_path, monkeypatch):
    repo, remote, platform, work = release(python_exe, tmp_path, monkeypatch)
    path = work / "changes/unreleased/1.3.0/objectives.md"
    before, after = path.read_text().split("- [ ] sync-remote", 1)
    path.write_text(before.replace("- [ ]", "- [x]") + "- [ ] sync-remote" + after)
    commit(work)
    git(work, "push", "origin", "HEAD:refs/heads/release/1.3.0")
    peer = tmp_path / "peer"
    git(tmp_path, "clone", "--branch", "release/1.3.0", str(remote), str(peer))
    return repo, remote, work, peer


def advance(peer, content="remote = True\n"):
    (peer / "src/service.py").write_text(content)
    commit(peer)
    git(peer, "push", "origin", "HEAD:refs/heads/release/1.3.0")
    return git(peer, "rev-parse", "HEAD").stdout.strip()


def complete(python_exe, work, head):
    return mdf(python_exe, "sync-remote", "--repo", str(work), "--complete",
               "--reviewed-head", head, "--summary", "已根据增量 plan 完成审查、验证及事实补检")


def test_remote_release_changes_require_incremental_validation(python_exe, tmp_path, monkeypatch):
    _repo, remote, work, peer = prepared(python_exe, tmp_path, monkeypatch)
    incoming = advance(peer)
    synced = payload(mdf(python_exe, "sync-remote", "--repo", str(work)))
    assert synced["completed"] is False and synced["remote"] == incoming
    objectives = (work / "changes/unreleased/1.3.0/objectives.md").read_text()
    for stage in ("lint", "code-review", "verify branch", "fact audit"):
        assert f"- [x] {stage}" in objectives
    assert "- [ ] sync-remote" in objectives and "- [ ] catch-up" in objectives
    assert synced["plan"]["review"]["action"] == "focused"
    assert synced["plan"]["verify"]["action"] == "smart"
    assert "src/service.py" in synced["plan"]["verify"]["paths"]
    assert (work / "src/service.py").read_text() == "remote = True\n"
    assert error_of(mdf(python_exe, "publish", "--repo", str(work)))["error"] == "stage_prerequisite"
    assert error_of(complete(python_exe, work, "0" * 40))["error"] == "sync_review_required"
    payload(complete(python_exe, work, synced["head"]))
    done = payload(mdf(python_exe, "publish", "--repo", str(work)))
    git(remote, "merge-base", "--is-ancestor", incoming, "v1.3.0")
    assert git(remote, "rev-parse", "release/1.3.0").stdout.strip() == done["release_head"]


def test_remote_advance_after_validation_returns_to_sync(python_exe, tmp_path, monkeypatch):
    _repo, _remote, work, peer = prepared(python_exe, tmp_path, monkeypatch)
    synced = payload(mdf(python_exe, "sync-remote", "--repo", str(work)))
    payload(complete(python_exe, work, synced["head"]))
    incoming = advance(peer)
    failed = error_of(mdf(python_exe, "publish", "--repo", str(work)))
    assert failed["error"] == "sync_remote_required"
    assert failed["details"]["next_intent"] == "sync-remote"
    synced = payload(mdf(python_exe, "sync-remote", "--repo", str(work)))
    assert synced["remote"] == incoming
    payload(complete(python_exe, work, synced["head"]))
    payload(mdf(python_exe, "publish", "--repo", str(work)))


def test_atomic_publish_rejects_concurrent_remote_commit_and_resumes(python_exe, tmp_path, monkeypatch):
    from mdf_core.lifecycle import publication_push
    _repo, remote, work, peer = prepared(python_exe, tmp_path, monkeypatch)
    synced = payload(mdf(python_exe, "sync-remote", "--repo", str(work)))
    payload(complete(python_exe, work, synced["head"]))
    original = publication_push.git
    incoming = []

    def race(repo, *args, **kwargs):
        if "push" in args and "--atomic" in args and not incoming:
            incoming.append(advance(peer))
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(publication_push, "git", race)
    failed = mdf(python_exe, "publish", "--repo", str(work))
    assert failed.returncode != 0
    assert run(["git", "rev-parse", "--verify", "v1.3.0"], cwd=remote).returncode != 0
    assert git(remote, "rev-parse", "release/1.3.0").stdout.strip() == incoming[0]
    synced = payload(mdf(python_exe, "sync-remote", "--repo", str(work)))
    payload(complete(python_exe, work, synced["head"]))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    git(remote, "merge-base", "--is-ancestor", incoming[0], "v1.3.0")


def test_diverged_release_conflict_preserves_original_validation_base(python_exe, tmp_path, monkeypatch):
    _repo, _remote, work, peer = prepared(python_exe, tmp_path, monkeypatch)
    (work / "src/service.py").write_text("local = True\n")
    commit(work)
    base = git(work, "rev-parse", "HEAD").stdout.strip()
    advance(peer)
    failed = error_of(mdf(python_exe, "sync-remote", "--repo", str(work)))
    assert failed["error"] == "merge_conflict"
    (work / "src/service.py").write_text("local = True\nremote = True\n")
    git(work, "add", "src/service.py")
    git(work, "commit", "-m", "test: 解决同名 release 冲突")
    synced = payload(mdf(python_exe, "sync-remote", "--repo", str(work)))
    assert synced["plan"]["base"] == base
    assert synced["plan"]["review"]["action"] == "focused"
    payload(complete(python_exe, work, synced["head"]))
