"""常驻 planning 分支与 worktree。"""
from mdf_test_support import *  # noqa: F403


def has_merge_head(repo: Path) -> bool:
    result = run(
        ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=repo
    )
    return result.returncode == 0


def parent_count(repo: Path) -> int:
    words = git(repo, "rev-list", "--parents", "-n1", "HEAD").stdout.split()
    return len(words) - 1


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
    assert parent_count(repo) == 1
    assert git(repo, "rev-parse", "HEAD").stdout == git(
        work, "rev-parse", "HEAD"
    ).stdout
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(repo, "show", "develop:planning-note.txt").stdout == "草稿\n"
    assert git(work, "branch", "--show-current").stdout.strip() == "planning"
    assert not has_merge_head(repo)
    assert not has_merge_head(work)
    again = payload(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))
    assert again["created"] is False
    assert not has_merge_head(work)


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


def test_empty_land_does_not_leave_merge_head_on_develop(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    (repo / "develop-only.txt").write_text("b\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "docs: develop 新提交")
    payload(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))
    assert parent_count(work) == 1
    assert git(work, "rev-parse", "HEAD").stdout == git(
        repo, "rev-parse", "HEAD"
    ).stdout
    result = payload(mdf(python_exe, "planning", "land", "--repo", str(work)))
    assert result["landed"] is False
    assert not has_merge_head(repo)
    (repo / "user.txt").write_text("c\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "feat: c")
    assert parent_count(repo) == 1


def test_git_is_clean_treats_sequencer_heads_as_dirty(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    (repo / "develop-only.txt").write_text("b\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "docs: develop 新提交")
    payload(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))
    (work / "temp.txt").write_text("t\n")
    git(work, "add", "--all")
    git(work, "commit", "-m", "docs: 临时")
    git(work, "rm", "temp.txt")
    git(work, "commit", "-m", "docs: 撤回临时")
    git(repo, "merge", "--no-ff", "--no-commit", "planning")
    assert not git(repo, "status", "--porcelain").stdout.strip()
    assert has_merge_head(repo)
    load_core_module()
    from mdf_core.gitutil import git_directory, git_is_clean

    assert git_is_clean(repo) is False
    doctor = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert doctor["clean"] is False
    land = mdf(python_exe, "planning", "land", "--repo", str(repo))
    assert land.returncode != 0
    assert "dirty_worktree" in land.stderr
    git(repo, "merge", "--abort")
    git_dir = git_directory(repo)
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    for name in ("CHERRY_PICK_HEAD", "REVERT_HEAD"):
        (git_dir / name).write_text(f"{sha}\n")
        assert git_is_clean(repo) is False
        (git_dir / name).unlink()
    assert git_is_clean(repo) is True


def test_diverged_planning_land_and_ensure_stay_no_ff(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    (work / "planning-note.txt").write_text("草稿\n")
    git(work, "add", "--all")
    git(work, "commit", "-m", "docs: 规划草稿")
    (repo / "develop-only.txt").write_text("b\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "docs: develop 新提交")
    result = payload(mdf(python_exe, "planning", "land", "--repo", str(work)))
    assert result["landed"] is True
    assert parent_count(repo) == 2
    assert git(repo, "log", "-1", "--format=%s").stdout.strip() == (
        "chore(planning): 合并 planning 到 develop"
    )
    assert git(repo, "show", "HEAD:planning-note.txt").stdout == "草稿\n"
    assert git(repo, "show", "HEAD:develop-only.txt").stdout == "b\n"
    (work / "again.txt").write_text("p\n")
    git(work, "add", "--all")
    git(work, "commit", "-m", "docs: 再次规划")
    (repo / "again-dev.txt").write_text("d\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "docs: 再次 develop")
    ensured = payload(
        mdf(python_exe, "planning", "ensure", "--repo", str(repo))
    )
    assert ensured["synced"] is True
    assert parent_count(work) == 2
    assert git(work, "log", "-1", "--format=%s").stdout.strip() == (
        "chore(planning): 合并 develop 到 planning"
    )


def test_merge_reports_unfinished_merge_not_conflict(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    (work / "planning-note.txt").write_text("草稿\n")
    git(work, "add", "--all")
    git(work, "commit", "-m", "docs: 规划草稿")
    (repo / "develop-only.txt").write_text("b\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "docs: develop 新提交")
    git(work, "merge", "--no-ff", "--no-commit", "develop")
    assert has_merge_head(work)
    load_core_module()
    from mdf_core.errors import MDFError
    from mdf_core.planning import merge_branch

    with pytest.raises(MDFError) as caught:
        merge_branch(work, "develop")
    assert caught.value.code == "unfinished_merge"
    assert has_merge_head(work)


def test_planning_ensure_aborts_real_conflict(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    (work / "note.txt").write_text("planning\n")
    git(work, "add", "--all")
    git(work, "commit", "-m", "docs: planning")
    (repo / "note.txt").write_text("develop\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "docs: develop")
    result = mdf(python_exe, "planning", "ensure", "--repo", str(repo))
    assert result.returncode != 0
    assert "merge_conflict" in result.stderr
    assert "unfinished_merge" not in result.stderr
    assert not has_merge_head(work)
