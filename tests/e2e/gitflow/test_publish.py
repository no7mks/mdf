"""finish-gitflow 发布的续办、恢复与分支前进保护。"""
from types import SimpleNamespace
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403
from support_upgrade import *  # noqa: F403


@pytest.mark.parametrize("after_push", [False, True])
@pytest.mark.parametrize("remote_develop_changed", [False, True])
def test_publish_resumes_without_remerging_or_retagging(
    python_exe, tmp_path, monkeypatch, after_push, remote_develop_changed,
):
    repo, remote = start_repo(tmp_path)
    created = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "hotfix",
        "--version", "1.2.1",
        "--objectives-file", str(write_work_objectives(tmp_path)),
    ))
    work = Path(created["worktree"])
    write_changelog_release(work, "1.2.1")
    (work / "src/service.py").write_text("fixed = True\n")
    commit(work)
    seed_consolidation(work)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    from mdf_core.lifecycle import pull_publish
    from mdf_core.lifecycle.release_publish import command_publish
    from mdf_core.foundation.errors import MDFError
    original = pull_publish.git

    def fail_push(repo, *args, **kwargs):
        if args and args[0] == "push":
            if after_push:
                original(repo, *args, **kwargs)
            raise MDFError("模拟推送结果丢失" if after_push else "模拟网络中断", code="test_interruption")
        return original(repo, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(pull_publish, "git", fail_push)
        with pytest.raises(MDFError):
            command_publish(SimpleNamespace(repo=str(work), source=None, pull=None))
    source = source_head(work)
    before = {ref: git(repo, "rev-parse", ref).stdout for ref in ("master", "v1.2.1")}
    if remote_develop_changed:
        other = tmp_path / "other"
        git(tmp_path, "clone", "--branch", "develop", str(remote), str(other))
        (other / "remote-development.txt").write_text("远端后续开发\n")
        commit(other)
        git(other, "push", "origin", "develop")
    remote_develop = git(remote, "rev-parse", "develop").stdout
    done = payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work)))
    assert done["pushed"] is True
    assert done["retained_worktree"] == str(work)
    assert done["primary_worktree"] == str(repo)
    assert source_head(work) == source
    assert work.is_dir()
    assert not git(work, "branch", "--show-current").stdout.strip()
    assert not git(repo, "for-each-ref", f"refs/heads/{created['branch']}").stdout
    for ref, head in before.items():
        assert git(repo, "rev-parse", ref).stdout == head
    assert git(remote, "rev-parse", "master").stdout == before["master"]
    assert git(remote, "rev-parse", "develop").stdout == remote_develop
    assert git(repo, "cat-file", "-t", "v1.2.1").stdout.strip() == "tag"
    assert git(repo, "rev-parse", "v1.2.1^{commit}").stdout.strip() == before["master"].strip()
    contents = git(
        repo, "tag", "-l", "--format=%(contents)", "v1.2.1"
    ).stdout
    assert contents.startswith("chore(release): 发布 v1.2.1")
    assert "测试发布条目" in contents
    # 从其他 linked worktree 恢复时，保留其分支并定位 detached owner。
    other_worktree = tmp_path / "other-worktree"
    git(repo, "worktree", "add", "-b", "other-work", str(other_worktree), "master")
    recovered = payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(other_worktree), "--source", "hotfix/1.2.1"))
    assert recovered["retained_worktree"] == str(work)
    assert git(other_worktree, "branch", "--show-current").stdout.strip() == "other-work"
    assert git(repo, "rev-parse", "v1.2.1").stdout == before["v1.2.1"]
    assert git(remote, "rev-parse", "develop").stdout == remote_develop
    assert work.is_dir()
    assert source_head(work) == source
    git(repo, "worktree", "remove", str(work))
    assert not work.exists()


@pytest.mark.parametrize("push_develop", [False, True])
def test_publish_recovers_unrecorded_develop_merge(python_exe, tmp_path, monkeypatch, push_develop):
    repo, remote = start_repo(tmp_path)
    created = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "hotfix",
        "--version", "1.2.1",
        "--objectives-file", str(write_work_objectives(tmp_path)),
    ))
    work = Path(created["worktree"])
    write_changelog_release(work, "1.2.1")
    (work / "src/service.py").write_text("fixed = True\n")
    commit(work)
    seed_consolidation(work)
    payload(mdf(python_exe, "merge", "--repo", str(work)))
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    load_core_module()
    from mdf_core.workspace import gitflow
    from mdf_core.foundation.errors import MDFError
    original = gitflow._merge

    def interrupt(repo_path, source, target, *args):
        original(repo_path, source, target, *args)
        if target == "develop":
            raise MDFError("模拟合并后中断", code="test_interruption")

    with monkeypatch.context() as patch:
        patch.setattr(gitflow, "_merge", interrupt)
        with pytest.raises(MDFError, match="模拟合并后中断"):
            gitflow.command_finish_gitflow(SimpleNamespace(repo=str(work), source=None))
    merged = git(repo, "rev-parse", "develop").stdout.strip()
    if push_develop:
        git(repo, "push", "origin", "develop")
    remote_develop = git(remote, "rev-parse", "develop").stdout.strip()
    assert payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work)))["pushed"] is True
    assert git(repo, "rev-parse", "develop").stdout.strip() == merged
    assert git(remote, "rev-parse", "develop").stdout.strip() == remote_develop


@pytest.mark.parametrize("kind", ["release", "hotfix"])
@pytest.mark.parametrize("advance,pushed", [
    ("develop", True), ("develop", False), ("master", True), ("master", False),
])
def test_publish_resume_after_dirty_worktree_and_branch_advance(
    python_exe, tmp_path, monkeypatch, kind, advance, pushed,
):
    repo, remote = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", kind,
                          "--version", "1.2.1",
                          "--objectives-file",
                          str(
                              write_release_objectives(tmp_path)
                              if kind == "release"
                              else write_work_objectives(tmp_path)
                          )))
    work = Path(created["worktree"])
    write_changelog_release(work, "1.2.1")
    (work / "src/service.py").write_text("fixed = True\n")
    commit(work)
    load_core_module()
    from mdf_core.workspace import gitflow
    dirty = repo / "dirty.txt"
    original_fetch = gitflow._fetch

    def fetch_then_dirty(worktree):
        original_fetch(worktree)
        # 模拟其他操作在首次只读预检之后写入；实际合并前仍须检查并保留。
        dirty.write_text("未提交\n")

    with monkeypatch.context() as patch:
        patch.setattr(gitflow, "_fetch", fetch_then_dirty)
        assert "dirty_worktree" in finish_delivery(python_exe, "finish-gitflow", "--repo", str(work)).stderr
    original_master = source_head(repo)
    dirty.unlink()
    git(repo, "checkout", advance)
    (repo / "development.txt").write_text("后续开发\n")
    commit(repo)
    advanced = source_head(repo)
    if pushed:
        git(repo, "push", "origin", advance)
    remote_develop = git(remote, "rev-parse", "develop").stdout.strip()
    result = finish_delivery(python_exe, "finish-gitflow", "--repo", str(work))
    if advance == "master" and not pushed:
        assert "publish_state_changed" in result.stderr
        assert git(remote, "rev-parse", advance).stdout.strip() == original_master
        return
    assert payload(result)["pushed"] is True
    assert git(repo, "show", "-s", "--format=%P", "develop").stdout.split()[-1] == git(repo, "rev-parse", "master").stdout.strip()
    if advance == "develop":
        assert git(repo, "rev-parse", "develop^1").stdout.strip() == advanced
    for ref in ("master", "refs/tags/v1.2.1"):
        assert git(remote, "rev-parse", ref).stdout == git(repo, "rev-parse", ref).stdout
    assert git(remote, "rev-parse", "develop").stdout.strip() == remote_develop
    assert work.is_dir()
    assert not git(work, "branch", "--show-current").stdout.strip()
    assert not git(repo, "for-each-ref", f"refs/heads/{kind}/1.2.1").stdout
