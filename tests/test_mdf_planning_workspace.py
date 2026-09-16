"""常驻 planning 分支与 worktree。"""

from mdf_test_support import *  # noqa: F403


def test_planning_ensure_reuses_one_worktree_and_keeps_develop(
    python_exe, tmp_path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    first = payload(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))
    work = Path(first["worktree"])
    assert first["created"] is True
    assert first["branch"] == "planning"
    assert work == repo.parent / f"{repo.name}-worktrees" / "planning"
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(work, "branch", "--show-current").stdout.strip() == "planning"
    again = payload(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))
    assert Path(again["worktree"]) == work
    assert again["created"] is False


def test_planning_land_updates_develop_without_stealing_checkout(
    python_exe, tmp_path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    (work / "planning-note.txt").write_text("草稿\n")
    git(work, "add", "--all")
    git(work, "commit", "-m", "docs: 规划草稿")
    result = payload(mdf(python_exe, "planning", "land", "--repo", str(work)))
    assert result["landed"] is True
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(repo, "show", "develop:planning-note.txt").stdout == "草稿\n"
    assert git(work, "branch", "--show-current").stdout.strip() == "planning"


def test_dirty_planning_does_not_block_feature_finish(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "-m", "master")
    git(repo, "checkout", "-b", "develop")
    created = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--bug", "bug-CD34",
    ))
    bugfix = Path(created["worktree"])
    (bugfix / "fix.txt").write_text("ok\n")
    git(bugfix, "add", "--all")
    git(bugfix, "commit", "-m", "fix: 文件")
    plan = planning_worktree(python_exe, repo)
    (plan / "review-wip.md").write_text("未提交评审\n")
    finished = payload(mdf(
        python_exe, "finish-gitflow", "--repo", str(bugfix),
    ))
    assert finished["ok"] is True
    assert not bugfix.exists()
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(repo, "show", "develop:fix.txt").stdout == "ok\n"
    assert (plan / "review-wip.md").is_file()
    assert git(plan, "branch", "--show-current").stdout.strip() == "planning"
