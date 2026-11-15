"""smoke / release 按 Git tree 复用，dirty 始终实跑。"""
from mdf_test_support import *  # noqa: F403


def verify(python_exe, repo, suite, *extra):
    return payload(mdf(python_exe, "verify", suite, "--repo", str(repo), *extra))["result"]["results"][0]


def test_smoke_and_release_have_independent_clear_commits(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    assert "clear_commit" not in verify(python_exe, repo, "smoke")
    assert verify(python_exe, repo, "smoke")["clear_commit"] == head
    assert "clear_commit" not in verify(python_exe, repo, "release")
    assert verify(python_exe, repo, "release")["clear_commit"] == head
    assert "clear_commit" not in verify(python_exe, repo, "smoke", "--force")
    assert json.loads((repo / ".git/mdf/clear-commits.json").read_text()) == {
        "verify_smoke": head, "verify_release": head,
    }


def test_dirty_runs_suite_without_moving_clear_commit(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    verify(python_exe, repo, "smoke")
    git(repo, "commit", "--allow-empty", "-m", "test: 改变 commit")
    git(repo, "config", "status.showUntrackedFiles", "no")
    (repo / "src/new.py").write_text("VALUE = 1\n")
    assert "clear_commit" not in verify(python_exe, repo, "smoke")
    assert json.loads((repo / ".git/mdf/clear-commits.json").read_text()) == {"verify_smoke": head}
    git(repo, "add", "src/new.py")
    git(repo, "commit", "-m", "feat: 增加实现")
    assert "clear_commit" not in verify(python_exe, repo, "smoke")
    assert verify(python_exe, repo, "smoke")["clear_commit"] != head


def test_failed_forced_suite_does_not_reuse_old_clear(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    marker = tmp_path / "fail-smoke"
    modules = repo / ".mdf/modules.yaml"
    text = modules.read_text()
    modules.write_text(text.replace('    smoke:\n      command: "',
                                    f'    smoke:\n      command: "test ! -f {marker} && '))
    init_git(repo)
    verify(python_exe, repo, "smoke")
    verify(python_exe, repo, "release")
    marker.touch()
    for args in (("--force",), ()):
        failed = mdf(python_exe, "verify", "smoke", "--repo", str(repo), *args)
        assert failed.returncode != 0 and "verify_command_failed" in failed.stderr
    state = json.loads((repo / ".git/mdf/clear-commits.json").read_text())
    assert set(state) == {"verify_release"}
