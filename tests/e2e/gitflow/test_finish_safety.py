"""finish 只读检查目标脏状态，保留既有 merge，发布前一次性检查所有目标。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403
from _support import run


def start_finishable(python_exe, tmp_path, kind):
    repo, remote = start_repo(tmp_path)
    git(repo, "checkout", "develop")
    git(repo, "worktree", "add", str(tmp_path / "deploy"), "master")
    if kind == "feature":
        from mdf_core.manual import STEPS
        obj = tmp_path / "manual.md"
        obj.write_text("# 目标\n\n" + "".join(
            f"- [{'x' if name == 'start' else ' '}] {name}\n" for name in STEPS
        ))
        extra = ["--manual", "--name", "manual-work"]
    else:
        obj = (write_release_objectives(tmp_path) if kind == "release"
               else write_work_objectives(tmp_path))
        extra = ["--bug", "bug-CD34"] if kind == "bugfix" else ["--version", "1.2.1"]
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", kind,
                       "--objectives-file", str(obj), *extra))
    work = Path(data["worktree"])
    if kind == "feature":
        root = work / "changes/unreleased/manual-work"
        (root / "objectives.md").write_text("# 目标\n\n" + "".join(
            f"- [x] {name}\n" for name in STEPS
        ))
        (root / "CHANGE.md").write_text(
            "---\nchange_kind: feature\nsource_branch: feature/manual-work\nproposals: []\n---\n成果\n"
        )
    elif kind in {"release", "hotfix"}:
        write_changelog_release(work, "1.2.1")
    (work / "finish.txt").write_text("本次交付\n")
    commit(work)
    return repo, remote, work


def snapshot(repo):
    git_dir = load_core_module().git_directory(repo)
    return {
        "content": (repo / "src/service.py").read_bytes(),
        "status": git(repo, "status", "--porcelain").stdout,
        "index": git(repo, "ls-files", "--stage").stdout,
        "refs": git(repo, "for-each-ref", "--format=%(refname) %(objectname)").stdout,
        "branch": git(repo, "branch", "--show-current").stdout,
        "merge": {name: (git_dir / name).read_bytes() for name in (
            "MERGE_HEAD", "MERGE_MSG", "ORIG_HEAD"
        ) if (git_dir / name).is_file()},
    }


@pytest.mark.parametrize("kind", ["feature", "bugfix", "release", "hotfix"])
@pytest.mark.parametrize("resolved", [False, True])
def test_finish_preserves_develop_origin_merge(python_exe, tmp_path, kind, resolved):
    repo, remote, work = start_finishable(python_exe, tmp_path, kind)
    path = repo / "src/service.py"
    git(repo, "checkout", "-b", "remote-side", "origin/develop")
    path.write_text("remote = True\n")
    commit(repo)
    git(repo, "push", "origin", "HEAD:develop")
    git(repo, "checkout", "develop")
    path.write_text("local = True\n")
    commit(repo)
    conflict = run(["git", "merge", "--no-ff", "--no-commit", "origin/develop"], cwd=repo)
    assert conflict.returncode == 1
    path.write_text("尚未 Commit 的人工解决结果\n")
    if resolved:
        git(repo, "add", "src/service.py")
    before = snapshot(repo)
    remote_before = git(remote, "show-ref").stdout
    result = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    assert result.returncode != 0 and "dirty_worktree" in result.stderr
    assert snapshot(repo) == before
    assert git(remote, "show-ref").stdout == remote_before
    assert git(work, "branch", "--show-current").stdout.strip() == f"{kind}/" + (
        "manual-work" if kind == "feature" else "bug-CD34" if kind == "bugfix" else "1.2.1"
    )


@pytest.mark.parametrize("kind", ["release", "hotfix"])
def test_publish_checks_dirty_develop_before_changing_master(python_exe, tmp_path, kind):
    repo, remote, work = start_finishable(python_exe, tmp_path, kind)
    (repo / "src/service.py").write_text("未提交的 develop 工作\n")
    before = snapshot(repo)
    remote_before = git(remote, "show-ref").stdout
    result = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    assert result.returncode != 0 and "dirty_worktree" in result.stderr
    assert snapshot(repo) == before
    assert git(remote, "show-ref").stdout == remote_before
    from mdf_core.publish import state_path
    assert not state_path(work, f"{kind}/1.2.1").exists()
