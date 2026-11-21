"""github-flow 的 deploy 保留 detached 部署 commit，不占用 trunk。"""
import pytest
from mdf_test_support import *  # noqa: F403
from support_github_flow import github_flow_repo


@pytest.mark.parametrize("trunk", ["master", "main"])
def test_deploy_detaches_and_preserves_commit_and_local_files(python_exe, tmp_path, trunk):
    repo = github_flow_repo(tmp_path, trunk=trunk)
    initial = git(repo, "rev-parse", "HEAD").stdout.strip()
    created = payload(mdf(python_exe, "to", "--repo", str(repo), "--target", "deploy"))
    work = Path(created["worktree"])
    assert created["branch"] == ""
    assert created["created"] is True
    assert git(work, "branch", "--show-current").stdout.strip() == ""
    assert git(work, "rev-parse", "HEAD").stdout.strip() == initial
    assert git(repo, "branch", "--show-current").stdout.strip() == trunk
    git(work, "commit", "--allow-empty", "-m", "test: 部署 commit")
    deployed = git(work, "rev-parse", "HEAD").stdout.strip()
    git(repo, "commit", "--allow-empty", "-m", "test: 推进 trunk")
    exclude = repo / ".git/info/exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text("deploy.local\n")
    (work / "deploy.local").write_text("config\n")
    (work / "scratch.txt").write_text("scratch\n")
    changelog = work / "CHANGELOG.md"
    changelog.write_text(changelog.read_text() + "\nlocal\n")
    again = payload(mdf(python_exe, "to", "--repo", str(work), "--target", "deploy"))
    assert again["created"] is False
    assert again["branch"] == ""
    assert Path(again["worktree"]) == work
    assert git(work, "rev-parse", "HEAD").stdout.strip() == deployed
    assert git(work, "branch", "--show-current").stdout.strip() == ""
    assert (work / "deploy.local").read_text() == "config\n"
    assert (work / "scratch.txt").read_text() == "scratch\n"
    assert changelog.read_text().endswith("\nlocal\n")


def test_deploy_detaches_existing_branch_only_when_clean(python_exe, tmp_path):
    repo = github_flow_repo(tmp_path)
    work = repo.parent / f"{repo.name}-worktrees" / "deploy"
    git(repo, "worktree", "add", "-b", "hold", str(work))
    git(work, "commit", "--allow-empty", "-m", "test: 部署 commit")
    deployed = git(work, "rev-parse", "HEAD").stdout.strip()
    changelog = work / "CHANGELOG.md"
    original = changelog.read_text()
    changelog.write_text(original + "\nlocal\n")
    result = mdf(python_exe, "to", "--repo", str(repo), "--target", "deploy")
    assert result.returncode != 0
    assert "dirty_worktree" in result.stderr
    assert git(work, "branch", "--show-current").stdout.strip() == "hold"
    changelog.write_text(original)
    result = payload(mdf(python_exe, "to", "--repo", str(repo), "--target", "deploy"))
    assert result["branch"] == ""
    assert result["created"] is False
    assert git(work, "branch", "--show-current").stdout.strip() == ""
    assert git(work, "rev-parse", "HEAD").stdout.strip() == deployed
