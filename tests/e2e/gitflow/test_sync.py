"""三大 trunk 与 origin 先拉后推。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def _error(result):
    assert result.returncode != 0
    return json.loads(result.stderr.strip().splitlines()[-1])


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

    result = payload(mdf(python_exe, "sync", "--repo", str(repo)))
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

    result = payload(mdf(python_exe, "sync", "--repo", str(repo)))
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
    failed = _error(mdf(python_exe, "sync", "--repo", str(repo)))
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
