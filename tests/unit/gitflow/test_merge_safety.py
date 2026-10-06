"""Gitflow 合并不得中止调用前已有的 merge 或清除人工解决结果。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import commit
from _support import run


@pytest.mark.parametrize("resolution", ["unstaged", "staged", "tree_clean"])
def test_merge_preserves_existing_merge(tmp_path, resolution):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    git(repo, "checkout", "-b", "incoming")
    path = repo / "src/service.py"
    path.write_text("incoming = True\n")
    commit(repo)
    git(repo, "checkout", "develop")
    path.write_text("local = True\n")
    commit(repo)
    conflict = run(["git", "merge", "--no-ff", "--no-commit", "incoming"], cwd=repo)
    assert conflict.returncode == 1
    path.write_text("local = True\n" if resolution == "tree_clean" else "人工解决结果\n")
    if resolution != "unstaged":
        git(repo, "add", "src/service.py")
    status = git(repo, "status", "--porcelain").stdout
    if resolution == "tree_clean":
        assert not status.strip()
    index = git(repo, "ls-files", "--stage").stdout
    content = path.read_bytes()
    merge_head = (repo / ".git/MERGE_HEAD").read_bytes()
    head = git(repo, "rev-parse", "HEAD").stdout
    load_core_module()
    from mdf_core.errors import MDFError
    from mdf_core.gitflow import _merge

    with pytest.raises(MDFError) as caught:
        _merge(repo, "incoming", "develop")
    assert caught.value.code == "dirty_worktree"
    assert path.read_bytes() == content
    assert (repo / ".git/MERGE_HEAD").read_bytes() == merge_head
    assert git(repo, "status", "--porcelain").stdout == status
    assert git(repo, "ls-files", "--stage").stdout == index
    assert git(repo, "rev-parse", "HEAD").stdout == head


def test_merge_does_not_abort_when_git_refuses_to_start(tmp_path, monkeypatch):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    load_core_module()
    from mdf_core import gitflow
    from mdf_core.errors import MDFError
    original = gitflow._git
    commands = []

    def refuse_merge(work, *args, **kwargs):
        commands.append(args)
        if args[:3] == ("merge", "--no-ff", "--no-commit"):
            return subprocess.CompletedProcess(args, 128, "", "Git 拒绝开始合并")
        return original(work, *args, **kwargs)

    monkeypatch.setattr(gitflow, "_git", refuse_merge)
    with pytest.raises(MDFError) as caught:
        gitflow._merge(repo, "HEAD", "main")
    assert caught.value.code == "command_failed"
    assert ("merge", "--abort") not in commands
