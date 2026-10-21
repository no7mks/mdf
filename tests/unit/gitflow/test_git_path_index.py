"""并行 evidence 共享 Git 缓存，独立路径可并行，同一路径只查询一次。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from mdf_test_support import *  # noqa: F403


def test_distinct_path_history_queries_overlap(monkeypatch, tmp_path):
    from mdf_core.workspace import gitutil

    barrier = Barrier(2, timeout=5)

    def history(repo, path):
        barrier.wait()
        return path.name

    monkeypatch.setattr(gitutil, "git_last_commit", history)
    index = gitutil.GitPathIndex(tmp_path)
    paths = [tmp_path / "a.py", tmp_path / "b.py"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(index.last_commit, paths)) == ["a.py", "b.py"]


def test_shared_path_history_is_queried_once(monkeypatch, tmp_path):
    from mdf_core.workspace import gitutil

    barrier = Barrier(4, timeout=5)
    calls = []

    def history(repo, path):
        calls.append(path)
        return "commit"

    monkeypatch.setattr(gitutil, "git_last_commit", history)
    index = gitutil.GitPathIndex(tmp_path)
    path = tmp_path / "shared.py"

    def query(_):
        barrier.wait()
        return index.last_commit(path)

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(query, range(4))) == ["commit"] * 4
    assert calls == [path]


@pytest.mark.parametrize("query,command,stdout,expected", [
    ("tracked", "ls-files", "src/service.py\0", True),
    ("dirty", "status", " M src/service.py\0", True),
])
def test_repository_state_is_loaded_once_under_concurrent_queries(
    query, command, stdout, expected, monkeypatch, tmp_path,
):
    from mdf_core.workspace import gitutil

    barrier = Barrier(4, timeout=5)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(gitutil, "run", run)
    index = gitutil.GitPathIndex(tmp_path)

    def check(_):
        barrier.wait()
        return getattr(index, query)(tmp_path / "src/service.py")

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(check, range(4))) == [expected] * 4
    assert len(calls) == 1
    assert calls[0][1] == command
