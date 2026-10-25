"""批量 history 与逐路径 Git 的结果一致，复杂 history 保留精确查询。"""
from concurrent.futures import ThreadPoolExecutor

from mdf_test_support import *  # noqa: F403


def commit(repo, message="test: 更新样本"):
    git(repo, "add", "--all")
    git(repo, "commit", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def assert_equivalent(repo, names):
    from mdf_core.workspace.gitutil import GitPathIndex, git_last_commit

    index = GitPathIndex(repo, batch_history=True)
    paths = [repo / name for name in names]
    expected = [git_last_commit(repo, path) for path in paths]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(index.last_commit, paths)) == expected
    return index


def test_bulk_history_handles_paths_directories_renames_and_empty_commits(tmp_path):
    from mdf_core.workspace.git_history import recent_path_commits

    repo = copy_fixture(tmp_path)
    names = ["src/空 格.py", "src/tab\tfile.py", "src/line\nfile.py", "src/cr\r\nfile.py", "src/renamed.py"]
    for name in names:
        (repo / name).write_text("VALUE = 1\n")
    init_git(repo)
    git(repo, "mv", "src/renamed.py", "src/destination.py")
    commit(repo)
    (repo / "src/service.py").unlink()
    deleted = commit(repo)
    commit(repo, "test: 空提交")
    index = assert_equivalent(repo, names + ["src", ".", "src/service.py", "src/destination.py", "src/absent.py"])
    assert index.last_commit(repo / "src/service.py") == deleted
    assert recent_path_commits(repo)["src/service.py"] == deleted


def test_bulk_history_does_not_treat_pathspec_as_literal(tmp_path):
    repo = copy_fixture(tmp_path)
    for name in ("src/literal*.py", "src/literal-other.py", "src/file[1].py", "src/file1.py"):
        (repo / name).write_text("VALUE = 1\n")
    init_git(repo)
    (repo / "src/literal-other.py").write_text("VALUE = 2\n")
    (repo / "src/file1.py").write_text("VALUE = 2\n")
    commit(repo)
    assert_equivalent(repo, ["src/literal*.py", "src/file[1].py", "src/file?.py"])


@pytest.mark.parametrize("merge_kind", ["normal", "ours", "conflict"])
def test_bulk_history_preserves_merge_simplification(tmp_path, merge_kind):
    from mdf_core.workspace.git_history import recent_path_commits

    repo = copy_fixture(tmp_path)
    init_git(repo)
    main = git(repo, "branch", "--show-current").stdout.strip()
    git(repo, "checkout", "-b", "side")
    (repo / "src/service.py").write_text("SIDE = 1\n")
    commit(repo)
    git(repo, "checkout", main)
    if merge_kind == "conflict":
        (repo / "src/service.py").write_text("MAIN = 1\n")
    else:
        (repo / "src/main.py").write_text("MAIN = 1\n")
    commit(repo)
    if merge_kind == "conflict":
        result = run(["git", "merge", "--no-ff", "side", "-m", "test: 合并"], cwd=repo)
        assert result.returncode != 0
        (repo / "src/service.py").write_text("RESOLVED = 1\n")
        commit(repo)
    else:
        extra = ["-s", "ours"] if merge_kind == "ours" else []
        git(repo, "merge", "--no-ff", *extra, "side", "-m", "test: 合并")
    assert recent_path_commits(repo) == {}
    assert_equivalent(repo, ["src/service.py", "src/main.py", "src", "."])
    (repo / "src/after.py").write_text("AFTER = 1\n")
    tip = commit(repo)
    assert recent_path_commits(repo) == {"src/after.py": tip, "src": tip, ".": tip}
    assert_equivalent(repo, ["src/after.py", "src/service.py", "src/main.py", "src", "."])


def test_bulk_history_is_bounded_and_old_paths_fall_back(tmp_path):
    from mdf_core.workspace.git_history import recent_path_commits

    repo = copy_fixture(tmp_path)
    init_git(repo)
    for _ in range(65):
        git(repo, "commit", "--allow-empty", "-m", "test: 空提交")
    assert recent_path_commits(repo) == {}
    assert_equivalent(repo, ["src/service.py", "src", "."])


def test_bulk_history_is_loaded_once_for_parallel_paths(monkeypatch, tmp_path):
    from mdf_core.workspace import git_history, gitutil

    calls = []
    paths = [tmp_path / f"src/{i}.py" for i in range(20)]

    def batch(repo):
        calls.append(repo)
        return {path.relative_to(repo).as_posix(): "commit" for path in paths}

    monkeypatch.setattr(git_history, "recent_path_commits", batch)
    index = gitutil.GitPathIndex(tmp_path, batch_history=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(index.last_commit, paths)) == ["commit"] * len(paths)
    assert calls == [tmp_path]


def test_bulk_failure_preserves_per_path_query(monkeypatch, tmp_path):
    from mdf_core.workspace import git_history, gitutil

    monkeypatch.setattr(git_history.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], 1, b"", b"error"))
    monkeypatch.setattr(gitutil, "git_last_commit", lambda repo, path: "exact-result")
    assert gitutil.GitPathIndex(tmp_path, batch_history=True).last_commit(tmp_path / "file") == "exact-result"


@pytest.mark.parametrize("ignore", ["none", "untracked", "dirty", "all"])
def test_bulk_history_preserves_gitlink_updates_under_diff_ignore(tmp_path, ignore):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    initial = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "deps").mkdir()
    (repo / "deps/README.md").write_text("dependency\n")
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{initial},deps/sub")
    git(repo, "add", "deps/README.md")
    git(repo, "commit", "-m", "test: 添加依赖")
    dependency = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "update-index", "--cacheinfo", f"160000,{dependency},deps/sub")
    git(repo, "commit", "-m", "test: 更新依赖")
    tip = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "config", "diff.ignoreSubmodules", ignore)
    index = assert_equivalent(repo, ["deps/sub", "deps", "."])
    assert index.last_commit(repo / "deps") == tip
