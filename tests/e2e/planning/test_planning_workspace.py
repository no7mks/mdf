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
    git(repo, "branch", "master")
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
    git(repo, "branch", "master")
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
        "--objectives-file", str(write_work_objectives(tmp_path)),
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
    assert bugfix.is_dir()
    assert not git(bugfix, "branch", "--show-current").stdout.strip()
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(repo, "show", "develop:fix.txt").stdout == "ok\n"
    assert (plan / "review-wip.md").is_file()
    assert git(plan, "branch", "--show-current").stdout.strip() == "planning"


def test_empty_land_does_not_leave_merge_head_on_develop(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "master")
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    (repo / "develop-only.txt").write_text("b\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "docs: develop 新提交")
    payload(mdf(python_exe, "planning", "ensure", "--repo", str(repo)))
    assert parent_count(work) == 0
    assert git(work, "rev-parse", "HEAD").stdout == git(
        repo, "rev-parse", "master"
    ).stdout
    assert not (work / "develop-only.txt").exists()
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
    git(repo, "branch", "master")
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
    from mdf_core.workspace.gitutil import git_directory, git_is_clean

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
    git(repo, "branch", "master")
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
        "chore(planning): 合并 master 到 develop"
    )
    assert git(repo, "show", "HEAD:planning-note.txt").stdout == "草稿\n"
    assert git(repo, "show", "HEAD:develop-only.txt").stdout == "b\n"
    (work / "again.txt").write_text("p\n")
    git(work, "add", "--all")
    git(work, "commit", "-m", "docs: 再次规划")
    master = repo.parent / f"{repo.name}-worktrees" / "master"
    (master / "again-master.md").write_text("d\n")
    git(master, "add", "--all")
    git(master, "commit", "-m", "docs: 再次 master")
    ensured = payload(
        mdf(python_exe, "planning", "ensure", "--repo", str(repo))
    )
    assert ensured["synced"] is True
    assert parent_count(work) == 2
    assert git(work, "log", "-1", "--format=%s").stdout.strip() == (
        "chore(planning): 合并 master 到 planning"
    )


def test_merge_reports_unfinished_merge_not_conflict(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "master")
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
    from mdf_core.foundation.errors import MDFError
    from mdf_core.workspace.planning import merge_branch

    with pytest.raises(MDFError) as caught:
        merge_branch(work, "develop")
    assert caught.value.code == "unfinished_merge"
    assert has_merge_head(work)


def test_planning_ensure_aborts_real_conflict(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "master")
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    (work / "note.txt").write_text("planning\n")
    git(work, "add", "--all")
    git(work, "commit", "-m", "docs: planning")
    git(repo, "checkout", "master")
    (repo / "note.txt").write_text("develop\n")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "docs: develop")
    result = mdf(python_exe, "planning", "ensure", "--repo", str(repo))
    assert result.returncode != 0
    assert "merge_conflict" in result.stderr
    assert "unfinished_merge" not in result.stderr
    assert not has_merge_head(work)


@pytest.mark.parametrize("mode", ["local", "pr"])
def test_planning_ff_both_trunks_and_keeps_develop_out_of_planning(python_exe, tmp_path, mode):
    from support_delivery import local_repo, commit
    repo = local_repo(tmp_path)
    if mode == "pr":
        manifest = repo / ".mdf/manifest.yaml"
        manifest.write_text(manifest.read_text() + "\ncloseout:\n  mode: pr\n  provider: github\n")
        commit(repo)
        git(repo, "branch", "-f", "develop", "master")
    work = planning_worktree(python_exe, repo)
    (work / "docs/plan.md").write_text("规划\n")
    commit(work)
    planned = git(work, "rev-parse", "HEAD").stdout
    payload(mdf(python_exe, "planning", "land", "--repo", str(work)))
    for branch in ("master", "develop", "planning"):
        assert git(repo, "rev-parse", branch).stdout == planned
    develop = repo.parent / f"{repo.name}-worktrees" / "develop"
    (develop / "pending.py").write_text("unreleased = True\n")
    commit(develop)
    (work / "docs/plan.md").write_text("新增规划\n")
    commit(work)
    payload(mdf(python_exe, "planning", "land", "--repo", str(work)))
    assert parent_count(develop) == 2
    assert not (work / "pending.py").exists() and not (repo / "pending.py").exists()
    git(repo, "merge-base", "--is-ancestor", "master", "develop")
    assert git(repo, "rev-parse", "master").stdout == git(repo, "rev-parse", "planning").stdout


def test_planning_diverged_same_tree_still_lands_history(python_exe, tmp_path):
    from support_delivery import local_repo, commit
    repo = local_repo(tmp_path)
    work = planning_worktree(python_exe, repo)
    (work / "docs/same.md").write_text("同一内容\n")
    commit(work, "docs: 规划内容")
    planned = git(work, "rev-parse", "HEAD").stdout.strip()
    (repo / "docs/same.md").write_text("同一内容\n")
    commit(repo, "docs: 主线内容")
    assert git(repo, "rev-parse", "HEAD^{tree}").stdout == git(work, "rev-parse", "HEAD^{tree}").stdout
    result = payload(mdf(python_exe, "planning", "land", "--repo", str(work)))
    assert result["landed"] and parent_count(repo) == 2
    for branch in ("master", "develop", "planning"):
        git(repo, "merge-base", "--is-ancestor", planned, branch)
