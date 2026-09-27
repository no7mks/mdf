"""merge-no-ff 的合并提交与冲突现场。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_merge_no_ff_commits_or_keeps_conflict(python_exe: str, tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--initial-branch=master", "--template=")
    git(repo, "commit", "--allow-empty", "-m", "base")
    git(repo, "checkout", "-b", "topic")
    (repo / "a.txt").write_text("topic\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-m", "topic")
    git(repo, "checkout", "master")
    merged = payload(
        mdf(python_exe, "merge-no-ff", "--repo", str(repo), "--commit", "topic")
    )
    assert merged["merged"] is True
    assert merged["branch"] == "master"

    again = payload(
        mdf(python_exe, "merge-no-ff", "--repo", str(repo), "--commit", "topic")
    )
    assert again["merged"] is False

    git(repo, "checkout", "-b", "left")
    (repo / "a.txt").write_text("left\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-m", "left")
    git(repo, "checkout", "master")
    git(repo, "checkout", "-b", "right")
    (repo / "a.txt").write_text("right\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-m", "right")
    conflict = mdf(
        python_exe, "merge-no-ff", "--repo", str(repo), "--commit", "left"
    )
    assert conflict.returncode != 0
    assert "merge_conflict" in conflict.stderr
    assert (repo / ".git" / "MERGE_HEAD").is_file()
