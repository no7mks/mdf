"""to：规划别名、develop 与已有分支 worktree。"""
from mdf_test_support import *  # noqa: F403


def test_to_plan_creates_planning_and_develop_reuses_primary(
    python_exe, tmp_path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "master")
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
    git(repo, "branch", "master")
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
    git(repo, "branch", "master")
    checkout_develop(repo)
    result = mdf(python_exe, "to", "--repo", str(repo), "--target", "missing")
    assert result.returncode != 0
    assert "unknown_target" in result.stderr
    assert "planning" in result.stderr
    assert "develop" in result.stderr
    assert "deploy" in result.stderr


def _with_master(tmp_path: Path) -> Path:
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    git(repo, "branch", "master")
    return repo


def _exclude(repo: Path, name: str) -> None:
    path = repo / ".git" / "info" / "exclude"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{name}\n", encoding="utf-8")


def test_to_deploy_checks_out_master_and_keeps_ignored_config(python_exe, tmp_path):
    repo = _with_master(tmp_path)
    _exclude(repo, "deploy.local")
    created = payload(mdf(
        python_exe, "to", "--repo", str(repo), "--target", "deploy",
    ))
    work = Path(created["worktree"])
    assert created["alias"] == "deploy"
    assert created["branch"] == "master"
    assert created["created"] is True
    assert work == repo.parent / f"{repo.name}-worktrees" / "deploy"
    assert git(work, "branch", "--show-current").stdout.strip() == "master"
    (work / "deploy.local").write_text("token\n", encoding="utf-8")
    (work / "scratch.txt").write_text("note\n", encoding="utf-8")
    git(work, "checkout", "-b", "hold")
    again = payload(mdf(
        python_exe, "to", "--repo", str(repo), "--target", "deploy",
    ))
    assert again["created"] is False
    assert again["branch"] == "master"
    assert git(work, "branch", "--show-current").stdout.strip() == "master"
    assert (work / "deploy.local").read_text(encoding="utf-8") == "token\n"
    assert (work / "scratch.txt").read_text(encoding="utf-8") == "note\n"


def test_to_deploy_stops_when_tracked_changes_exist(python_exe, tmp_path):
    repo = _with_master(tmp_path)
    created = payload(mdf(
        python_exe, "to", "--repo", str(repo), "--target", "deploy",
    ))
    work = Path(created["worktree"])
    git(work, "checkout", "-b", "hold")
    changelog = work / "CHANGELOG.md"
    changelog.write_text(
        changelog.read_text(encoding="utf-8") + "\nlocal\n", encoding="utf-8",
    )
    result = mdf(python_exe, "to", "--repo", str(repo), "--target", "deploy")
    assert result.returncode != 0
    assert "dirty_worktree" in result.stderr
    assert git(work, "branch", "--show-current").stdout.strip() == "hold"


def test_to_deploy_stops_when_master_is_occupied(python_exe, tmp_path):
    repo = _with_master(tmp_path)
    git(repo, "checkout", "master")
    result = mdf(python_exe, "to", "--repo", str(repo), "--target", "deploy")
    assert result.returncode != 0
    assert "master_occupied" in result.stderr


def test_to_deploy_requires_master_branch(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    result = mdf(python_exe, "to", "--repo", str(repo), "--target", "deploy")
    assert result.returncode != 0
    assert "missing_branch" in result.stderr
