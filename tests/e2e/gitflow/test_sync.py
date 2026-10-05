"""三大 trunk 与 origin 先拉后推。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def _error(result):
    assert result.returncode != 0
    return json.loads(result.stderr.strip().splitlines()[-1])


def _sync(python_exe, repo):
    preview = payload(mdf(python_exe, "sync", "--repo", str(repo)))
    return mdf(python_exe, "sync", "--repo", str(repo), "--confirm", preview["confirmation"])


def _trunk_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo, remote = start_repo(tmp_path)
    git(repo, "branch", "planning", "develop")
    git(repo, "push", "-u", "origin", "planning")
    return repo, remote


def _advance_origin(remote: Path, branch: str, tmp_path: Path) -> None:
    other = tmp_path / f"ahead-{branch}"
    git(tmp_path, "clone", "--branch", branch, str(remote), str(other))
    (other / f"{branch}-remote.txt").write_text("远程更新\n", encoding="utf-8")
    commit(other, f"test: 远程推进 {branch}")
    git(other, "push")


def test_sync_ff_pull_then_push_and_reports_extras(python_exe: str, tmp_path: Path):
    repo, remote = _trunk_repo(tmp_path)
    git(repo, "branch", "feature/leftover")
    other = tmp_path / "remote-extra"
    git(tmp_path, "clone", str(remote), str(other))
    git(other, "checkout", "-b", "legacy")
    (other / "legacy.txt").write_text("远端多余\n", encoding="utf-8")
    commit(other, "test: 远端多余分支")
    git(other, "push", "-u", "origin", "legacy")

    _advance_origin(remote, "develop", tmp_path)
    git(repo, "checkout", "master")
    (repo / "local-master.txt").write_text("本地领先\n", encoding="utf-8")
    commit(repo, "test: 本地领先 master")

    result = payload(_sync(python_exe, repo))
    assert result["operation"] == "sync"
    assert result["trunks"]["develop"]["pull"] == "ff"
    assert result["trunks"]["master"]["pull"] == "noop"
    assert result["trunks"]["master"]["push"] == "updated"
    assert result["trunks"]["planning"]["pull"] == "noop"
    assert "feature/leftover" in result["extra_local"]
    assert "legacy" in result["extra_remote"]
    assert git(repo, "rev-parse", "master").stdout.strip() == git(
        repo, "rev-parse", "origin/master"
    ).stdout.strip()
    assert git(repo, "rev-parse", "develop").stdout.strip() == git(
        repo, "ls-remote", remote, "refs/heads/develop"
    ).stdout.split()[0]


def test_sync_merges_diverged_trunk(python_exe: str, tmp_path: Path):
    repo, remote = _trunk_repo(tmp_path)
    _advance_origin(remote, "planning", tmp_path)
    git(repo, "checkout", "planning")
    (repo / "local-planning.txt").write_text("本地分叉\n", encoding="utf-8")
    commit(repo, "test: 本地分叉 planning")
    git(repo, "checkout", "develop")

    result = payload(_sync(python_exe, repo))
    assert result["trunks"]["planning"]["pull"] == "merged"
    assert result["trunks"]["planning"]["push"] == "updated"
    parents = git(
        repo, "show", "-s", "--format=%P", "planning"
    ).stdout.split()
    assert len(parents) == 2


def test_sync_rejects_dirty_trunk_worktree(python_exe: str, tmp_path: Path):
    repo, _remote = _trunk_repo(tmp_path)
    git(repo, "checkout", "develop")
    (repo / "dirty.txt").write_text("脏\n", encoding="utf-8")
    failed = _error(_sync(python_exe, repo))
    assert failed["error"] == "dirty_worktree"


def test_sync_requires_both_sides(python_exe: str, tmp_path: Path):
    repo, remote = start_repo(tmp_path)
    git(repo, "branch", "planning", "develop")
    failed = _error(mdf(python_exe, "sync", "--repo", str(repo)))
    assert failed["error"] == "missing_upstream_branch"
    assert "planning" in failed["message"]
    # 远端缺少 planning 时不得创建该远端分支。
    listed = git(remote, "for-each-ref", "--format=%(refname)", "refs/heads")
    assert "refs/heads/planning" not in listed.stdout


def test_sync_preview_graphs_all_relations_without_merging_or_pushing(python_exe, tmp_path):
    repo, remote = _trunk_repo(tmp_path)
    for branch in ("develop", "planning"):
        _advance_origin(remote, branch, tmp_path)
    for branch in ("master", "planning"):
        git(repo, "checkout", branch)
        (repo / f"{branch}-local.txt").write_text("local\n")
        commit(repo, f"test: 推进 {branch}")
    git(repo, "branch", "feature/local")
    git(remote, "branch", "feature/remote", "master")
    before = {b: git(repo, "rev-parse", b).stdout for b in ("master", "develop", "planning")}
    origin = git(remote, "show-ref").stdout
    result = payload(mdf(python_exe, "sync", "--repo", str(repo)))
    assert result["operation"] == "sync-preview"
    branches = result["branches"]
    assert branches["master"]["relation"] == "ahead"
    assert branches["develop"]["relation"] == "behind"
    assert branches["planning"]["relation"] == "diverged"
    assert branches["planning"]["ahead"] == branches["planning"]["behind"] == 1
    assert branches["feature/local"]["relation"] == "local_only"
    assert branches["feature/remote"]["relation"] == "remote_only"
    assert not branches["feature/local"]["sync"]
    for branch in before:
        assert git(repo, "rev-parse", branch).stdout == before[branch]
        assert f"refs/heads/{branch}" in branches[branch]["graph"]
        assert f"refs/remotes/origin/{branch}" in branches[branch]["graph"]
    assert git(remote, "show-ref").stdout == origin
    assert git(repo, "branch", "--show-current").stdout.strip() == "planning"


def test_sync_equal_preview_and_stale_confirmation(python_exe, tmp_path):
    repo, remote = _trunk_repo(tmp_path)
    preview = payload(mdf(python_exe, "sync", "--repo", str(repo)))
    assert all(info["relation"] == "equal" for info in preview["branches"].values())
    _advance_origin(remote, "master", tmp_path)
    local = git(repo, "rev-parse", "master").stdout
    failed = _error(mdf(python_exe, "sync", "--repo", str(repo),
                        "--confirm", preview["confirmation"]))
    assert failed["error"] == "sync_plan_changed"
    assert failed["details"]["branches"]["master"]["relation"] == "behind"
    assert git(repo, "rev-parse", "master").stdout == local


@pytest.mark.parametrize("filename", ["shared.txt", "共享文件.txt"])
def test_sync_conflict_preserves_scene_and_can_resume_after_resolution(python_exe, tmp_path, filename):
    repo, remote = _trunk_repo(tmp_path)
    git(repo, "checkout", "planning")
    (repo / filename).write_text("base\n")
    commit(repo, "test: 共同文件")
    git(repo, "push", "origin", "planning")
    other = tmp_path / "conflicting"
    git(tmp_path, "clone", "--branch", "planning", str(remote), str(other))
    (other / filename).write_text("remote\n")
    commit(other, "test: 远端修改")
    git(other, "push")
    (repo / filename).write_text("local\n")
    commit(repo, "test: 本地修改")
    git(repo, "checkout", "develop")
    before_remote = git(remote, "show-ref").stdout
    git(repo, "config", "core.quotePath", "true")
    failed = _error(_sync(python_exe, repo))
    assert failed["error"] == "merge_conflict"
    assert failed["details"]["worktree"] == str(repo)
    assert failed["details"]["branch"] == "planning"
    assert failed["details"]["conflicts"] == [filename]
    assert git(repo, "rev-parse", "MERGE_HEAD").stdout.strip()
    assert git(repo, "branch", "--show-current").stdout.strip() == "planning"
    assert "<<<<<<<" in (repo / filename).read_text()
    assert git(remote, "show-ref").stdout == before_remote
    (repo / filename).write_text("local\nremote\n")
    commit(repo, "chore(sync): 合并 origin/planning 到 planning")
    result = payload(_sync(python_exe, repo))
    assert result["trunks"]["planning"]["pull"] == "noop"
    assert result["trunks"]["planning"]["push"] == "updated"
    assert git(remote, "show", f"planning:{filename}").stdout == "local\nremote\n"


def test_sync_merges_diverged_history_with_identical_trees(python_exe, tmp_path):
    repo, remote = _trunk_repo(tmp_path)
    other = tmp_path / "empty-remote"
    git(tmp_path, "clone", "--branch", "planning", str(remote), str(other))
    git(other, "commit", "--allow-empty", "-m", "test: 远端空提交")
    git(other, "push")
    git(repo, "checkout", "planning")
    git(repo, "commit", "--allow-empty", "-m", "test: 本地空提交")
    result = payload(_sync(python_exe, repo))
    assert result["trunks"]["planning"]["pull"] == "merged"
    assert len(git(repo, "show", "-s", "--format=%P", "planning").stdout.split()) == 2


def test_sync_confirmed_refs_are_unambiguous_and_do_not_push_tags(python_exe, tmp_path):
    repo, remote = _trunk_repo(tmp_path)
    _advance_origin(remote, "planning", tmp_path)
    git(repo, "branch", "origin/planning", "planning")
    git(repo, "checkout", "master")
    git(repo, "commit", "--allow-empty", "-m", "test: 本地推进")
    git(repo, "tag", "master")
    git(repo, "tag", "-a", "unrelated-tag", "-m", "test: 其他 tag")
    git(repo, "config", "push.followTags", "true")
    result = payload(_sync(python_exe, repo))
    assert result["trunks"]["planning"]["pull"] == "ff"
    assert git(repo, "rev-parse", "refs/heads/planning").stdout == git(
        remote, "rev-parse", "refs/heads/planning"
    ).stdout
    assert not git(remote, "for-each-ref", "refs/tags").stdout.strip()


def test_sync_rejects_confirmation_after_push_destination_changes(python_exe, tmp_path):
    repo, remote = _trunk_repo(tmp_path)
    preview = payload(mdf(python_exe, "sync", "--repo", str(repo)))
    other_remote = tmp_path / "other.git"
    git(tmp_path, "clone", "--bare", str(remote), str(other_remote))
    git(repo, "remote", "set-url", "--push", "origin", str(other_remote))
    failed = _error(mdf(python_exe, "sync", "--repo", str(repo),
                        "--confirm", preview["confirmation"]))
    assert failed["error"] == "sync_plan_changed"


def test_sync_graph_keeps_both_tips_when_far_apart(python_exe, tmp_path):
    repo, _remote = _trunk_repo(tmp_path)
    for index in range(14):
        git(repo, "commit", "--allow-empty", "-m", f"test: 本地推进 {index}")
    preview = payload(mdf(python_exe, "sync", "--repo", str(repo)))
    master = preview["branches"]["master"]
    assert master["ahead"] == 14
    assert "refs/heads/master" in master["graph"]
    assert "refs/remotes/origin/master" in master["graph"]
