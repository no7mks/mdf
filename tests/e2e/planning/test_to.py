"""to：规划别名、develop 与已有分支 worktree。"""
from mdf_test_support import *  # noqa: F403


def test_to_plan_creates_planning_and_develop_reuses_primary(
    python_exe, tmp_path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    created = payload(mdf(
        python_exe, "to", "--repo", str(repo), "--target", "plan",
    ))
    work = Path(created["worktree"])
    assert created["alias"] == "planning"
    assert created["branch"] == "planning"
    assert created["created"] is True
    assert work == repo.parent / f"{repo.name}-worktrees" / "planning"
    again = payload(mdf(
        python_exe, "to", "--repo", str(repo), "--target", "plan-mode",
    ))
    assert Path(again["worktree"]) == work
    assert again["created"] is False
    develop = payload(mdf(
        python_exe, "to", "--repo", str(repo), "--target", "develop",
    ))
    assert develop["alias"] == "develop"
    assert develop["branch"] == "develop"
    assert develop["created"] is False
    assert Path(develop["worktree"]).resolve() == repo.resolve()


def test_to_existing_branch_adds_sibling_worktree(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    git(repo, "branch", "topic/demo")
    created = payload(mdf(
        python_exe, "to", "--repo", str(repo), "--target", "topic/demo",
    ))
    work = Path(created["worktree"])
    assert created["created"] is True
    assert created["branch"] == "topic/demo"
    assert work == repo.parent / f"{repo.name}-worktrees" / "topic" / "demo"
    assert git(work, "branch", "--show-current").stdout.strip() == "topic/demo"
    again = payload(mdf(
        python_exe, "to", "--repo", str(repo), "--target", "topic/demo",
    ))
    assert Path(again["worktree"]) == work
    assert again["created"] is False


def test_to_unknown_target_lists_aliases(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    result = mdf(python_exe, "to", "--repo", str(repo), "--target", "missing")
    assert result.returncode != 0
    assert "unknown_target" in result.stderr
    assert "planning" in result.stderr
    assert "develop" in result.stderr
