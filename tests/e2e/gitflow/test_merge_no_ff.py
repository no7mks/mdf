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


def test_merge_no_ff_reads_only_committed_develop_tip(python_exe, tmp_path):
    from support_delivery import commit, local_repo

    develop = local_repo(tmp_path)
    git(develop, "switch", "develop")
    objectives = tmp_path / "objectives.md"
    objectives.write_text("# 目标\n\n- needs_design: yes\n")
    started = payload(mdf(python_exe, "start", "--repo", str(develop), "--kind", "feature",
                          "--proposal", "prp-0001", "--objectives-file", str(objectives)))
    owner = Path(started["worktree"])
    upstream = develop / "upstream.txt"
    upstream.write_text("已提交\n")
    commit(develop, "test: 推进 develop")
    tip = git(develop, "rev-parse", "HEAD").stdout.strip()
    owner_tip = git(owner, "rev-parse", "HEAD").stdout.strip()
    upstream.write_text("已暂存\n")
    git(develop, "add", "--", upstream.name)
    upstream.write_text("未暂存\n")
    (develop / "scratch.txt").write_text("未跟踪\n")

    merged = payload(mdf(python_exe, "merge-no-ff", "--repo", str(owner), "--commit", tip))

    assert merged["merged"] is True
    assert git(owner, "show", "-s", "--format=%P", "HEAD").stdout.split() == [owner_tip, tip]
    assert (owner / upstream.name).read_text() == "已提交\n"
    assert not (owner / "scratch.txt").exists()
    assert git(develop, "rev-parse", "HEAD").stdout.strip() == tip
    assert git(develop, "show", f":{upstream.name}").stdout == "已暂存\n"
    assert upstream.read_text() == "未暂存\n"
    assert (develop / "scratch.txt").read_text() == "未跟踪\n"
