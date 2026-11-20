"""发布更新清单、hook 保留和阶段提交的恢复。"""
from mdf_test_support import *  # noqa: F403
from support_github_flow import error_of
from test_sync_remote import prepared, complete


def ready(python_exe, tmp_path, monkeypatch):
    repo, remote, work, peer = prepared(python_exe, tmp_path, monkeypatch)
    synced = payload(mdf(python_exe, "sync-remote", "--repo", str(work)))
    payload(complete(python_exe, work, synced["head"]))
    return repo, remote, work, peer


def hook_path(work, name):
    common = Path(git(work, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    path = common / "hooks" / name
    path.parent.mkdir(exist_ok=True)
    return path


def test_noop_release_update_cannot_publish_tag(python_exe, tmp_path, monkeypatch):
    from mdf_core.lifecycle import publication_push
    _repo, remote, work, _peer = ready(python_exe, tmp_path, monkeypatch)
    original = publication_push.git
    pushed = []

    def race(repo, *args, **kwargs):
        if "push" in args and "--atomic" in args and not pushed:
            git(work, "push", "origin", "HEAD:refs/heads/release/1.3.0")
            pushed.append(True)
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(publication_push, "git", race)
    failed = mdf(python_exe, "publish", "--repo", str(work))
    assert failed.returncode != 0 and pushed
    assert run(["git", "rev-parse", "--verify", "v1.3.0"], cwd=remote).returncode != 0
    synced = payload(mdf(python_exe, "sync-remote", "--repo", str(work)))
    payload(complete(python_exe, work, synced["head"]))
    payload(mdf(python_exe, "publish", "--repo", str(work)))


@pytest.mark.parametrize("foreign", [False, True])
def test_publish_resumes_own_failed_commit_only(python_exe, tmp_path, monkeypatch, foreign):
    _repo, remote, work, _peer = ready(python_exe, tmp_path, monkeypatch)
    hook = hook_path(work, "pre-commit")
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    failed = mdf(python_exe, "publish", "--repo", str(work))
    assert error_of(failed)["error"] == "command_failed"
    tag = git(remote, "rev-parse", "v1.3.0").stdout
    hook.unlink()
    if foreign:
        (work / "src/service.py").write_text("foreign = True\n")
        assert error_of(mdf(python_exe, "publish", "--repo", str(work)))["error"] == "dirty_worktree"
        assert (work / "src/service.py").read_text() == "foreign = True\n"
    else:
        done = payload(mdf(python_exe, "publish", "--repo", str(work)))
        assert done["completed"]
        assert not git(work, "status", "--porcelain").stdout
    assert git(remote, "rev-parse", "v1.3.0").stdout == tag


@pytest.mark.parametrize("reject", [False, True])
def test_original_pre_push_hook_receives_same_updates(python_exe, tmp_path, monkeypatch, reject):
    _repo, remote, work, _peer = ready(python_exe, tmp_path, monkeypatch)
    hooks = work / ".local-hooks"
    hooks.mkdir()
    git(work, "config", "core.hooksPath", str(hooks))
    # hook 与记录位于被忽略的测试目录，工作区保持 clean。
    exclude = Path(git(work, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude").stdout.strip())
    exclude.parent.mkdir(exist_ok=True)
    with exclude.open("a") as stream:
        stream.write("\n.local-hooks/\n")
    hook = hooks / "pre-push"
    hook.write_text('#!/bin/sh\ncat > "' + str(hooks / 'updates') + '"\nexit ' + str(int(reject)) + '\n')
    hook.chmod(0o755)
    result = mdf(python_exe, "publish", "--repo", str(work))
    assert (result.returncode != 0) == reject
    updates = (hooks / "updates").read_text()
    assert "refs/heads/release/1.3.0" in updates and "refs/tags/v1.3.0" in updates
    assert (run(["git", "rev-parse", "--verify", "v1.3.0"], cwd=remote).returncode != 0) == reject


def test_sync_completion_retries_and_remains_idempotent(python_exe, tmp_path, monkeypatch):
    _repo, _remote, work, _peer = prepared(python_exe, tmp_path, monkeypatch)
    synced = payload(mdf(python_exe, "sync-remote", "--repo", str(work)))
    hook = hook_path(work, "pre-commit")
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    assert error_of(complete(python_exe, work, synced["head"]))["error"] == "command_failed"
    hook.unlink()
    done = payload(complete(python_exe, work, synced["head"]))
    again = payload(complete(python_exe, work, done["head"]))
    assert again["head"] == done["head"]
    assert not git(work, "status", "--porcelain").stdout
