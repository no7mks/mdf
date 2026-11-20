"""首次 support PR 创建远端维护线基线，不绕过 PR 发布修复。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from support_pull import Platform
from test_support_consolidate import prepare_hotfix, consolidate_hotfix


@pytest.mark.parametrize("entry", ["incremental-integration", "pr"])
def test_first_support_pr_bootstraps_exact_start_commit(python_exe, tmp_path, monkeypatch, entry):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    consolidate_hotfix(python_exe, work, change)
    identity = json.loads((work / "changes/1.2.1/delivery.json").read_text())
    start = identity["start_commit"]
    published = payload(mdf(python_exe, "publish", "--repo", str(work)))
    assert git(remote, "branch", "--list", "support/1.2").stdout == ""
    assert start != published["release_head"]
    # 本地同名 support 后续变化不能成为创建远端的基线。
    git(repo, "update-ref", "refs/heads/support/1.2", published["release_head"])
    platform = Platform()
    platform.repo, platform.remote = repo, remote
    from mdf_core.lifecycle import pull_finish
    forge_identity = {"provider": "github", "host": "forge.invalid", "project": "team/project", "origin": str(remote)}
    monkeypatch.setattr(pull_finish, "origin", lambda *_: forge_identity)
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    integrated = payload(mdf(python_exe, entry, "--repo", str(work)))
    if entry == "incremental-integration":
        assert integrated["completed"] is True
    assert git(remote, "rev-parse", "support/1.2").stdout.strip() == start
    payload(mdf(python_exe, "pr", "--repo", str(work)))
    payload(mdf(python_exe, "pr", "--repo", str(repo), "--source", "hotfix/1.2.1"))
    assert platform.pulls[0]["target"] == "support/1.2"
    assert git(remote, "rev-parse", "support/1.2").stdout.strip() == start
    platform.merge(1, tmp_path)
    payload(mdf(python_exe, "pr", "--repo", str(work)))
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert git(remote, "rev-parse", "v1.2.1^{commit}").stdout.strip() == published["release_head"]


def test_existing_remote_support_is_integrated_without_overwrite(python_exe, tmp_path):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    other = tmp_path / "other-support"
    git(repo, "worktree", "add", str(other), "support/1.2")
    (other / "src/remote_fix.py").write_text("fixed = True\n")
    commit(other)
    target = git(other, "rev-parse", "HEAD").stdout.strip()
    git(other, "push", "origin", "support/1.2")
    result = payload(mdf(python_exe, "incremental-integration", "--repo", str(work)))
    assert result["completed"] is False
    assert (work / "src/remote_fix.py").is_file()
    assert git(remote, "rev-parse", "support/1.2").stdout.strip() == target
    git(work, "merge-base", "--is-ancestor", target, "HEAD")


def test_competing_remote_support_creation_is_preserved(python_exe, tmp_path, monkeypatch):
    repo, remote, work, change = prepare_hotfix(python_exe, tmp_path, pr=True)
    consolidate_hotfix(python_exe, work, change)
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    other = tmp_path / "racing-support"
    git(repo, "worktree", "add", str(other), "support/1.2")
    (other / "src/competitor.py").write_text("fixed = True\n")
    commit(other)
    target = git(other, "rev-parse", "HEAD").stdout.strip()
    # 先传对象到普通临时ref，随后在helper的create-only push前创建目标。
    git(other, "push", "origin", f"{target}:refs/heads/competitor")
    from mdf_core.lifecycle import support_line
    original = support_line._git
    raced = []

    def racing(repo, *args, **kwargs):
        if args[0] == "push" and not raced:
            raced.append(True)
            assert "--force-with-lease=refs/heads/support/1.2:" in args
            git(remote, "update-ref", "refs/heads/support/1.2", target)
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(support_line, "_git", racing)
    result = payload(mdf(python_exe, "incremental-integration", "--repo", str(work)))
    assert raced and result["completed"] is False
    assert (work / "src/competitor.py").is_file()
    assert git(remote, "rev-parse", "support/1.2").stdout.strip() == target
