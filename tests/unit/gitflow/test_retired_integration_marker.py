"""普通 commit trailer 不构成当前 squash 保护边界。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import local_repo, commit


def test_release_head_trailer_does_not_protect_an_unshared_commit(tmp_path):
    from mdf_core.workspace.squash import inspect
    repo = local_repo(tmp_path)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-b", "feature/example")
    (repo / "first.txt").write_text("第一项\n")
    commit(repo)
    (repo / "second.txt").write_text("第二项\n")
    commit(repo, "docs: 普通记录\n\nMDF-Release-Head: " + base)
    plan = inspect(repo, refresh=False)
    assert plan["floor"] == base and len(plan["commits"]) == 2
