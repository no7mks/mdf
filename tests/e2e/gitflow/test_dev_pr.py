"""develop 接管、项目 trivial policy 与检查前零远端写入。"""
from pathlib import Path

import pytest

from mdf_core.foundation.errors import MDFError
from mdf_core.workspace import dev_pr
from mdf_test_support import git, mdf, payload
from support_delivery import commit
from support_sync import prepare, sync


@pytest.mark.parametrize("provider", ["github", "gitlab"])
@pytest.mark.parametrize("diverged", [False, True])
def test_dev_pr_preserves_work_then_reuses_adhoc_pr(python_exe, tmp_path, monkeypatch, provider, diverged):
    repo, remote, platform = prepare(tmp_path, monkeypatch, provider, ("develop",), diverged)
    head = git(repo, "rev-parse", "develop").stdout.strip()
    refs = git(remote, "show-ref").stdout
    result = payload(sync(python_exe, repo))
    assert result["status"] == "dev_pr_required"
    state = result["pull_requests"]["develop"]
    work, source = Path(state["worktree"]), state["source"]
    assert git(work, "rev-parse", "HEAD").stdout.strip() == head
    assert (work / "develop-local.txt").is_file() and not (repo / "develop-local.txt").exists()
    assert git(repo, "rev-parse", "develop").stdout == git(remote, "rev-parse", "develop").stdout
    assert git(remote, "show-ref").stdout == refs and platform.pulls == []
    assert payload(sync(python_exe, repo))["pull_requests"]["develop"]["source"] == source
    assert payload(mdf(python_exe, "dev-pr", "--repo", str(repo)))["result"]["source"] == source
    # 模拟 intent 已完成检查后提交真实 Change，平台和 Git 生命周期复用既有 pr。
    from mdf_core.lifecycle import pull_finish
    from support_pull import squash_pending
    from test_untracked_adhoc import write_change
    monkeypatch.setattr(pull_finish, "origin", lambda *_: {
        "provider": provider, "host": "forge.invalid", "project": "team/project", "origin": str(remote),
    })
    monkeypatch.setattr(pull_finish, "Forge", lambda *_: platform)
    git(work, "merge", "--no-ff", "origin/develop", "-m", "test: 集成远端")
    write_change(work, source, source.split("/", 1)[1])
    commit(work)
    squash_pending(work)
    assert payload(mdf(python_exe, "pr", "--repo", str(work)))["status"] == "waiting_for_merge"
    assert payload(mdf(python_exe, "pr", "--repo", str(work)))["status"] == "waiting_for_merge"
    assert len(platform.pulls) == 1
    merged = platform.merge(1, tmp_path)
    assert payload(mdf(python_exe, "pr", "--repo", str(work)))["completed"]
    assert payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", source))["completed"]
    assert git(repo, "rev-parse", "develop").stdout.strip() == merged
    assert payload(sync(python_exe, repo, pr=False))["trunks"]["develop"]["push"] == "noop"


@pytest.mark.parametrize("boundary", ["record", "branch", "worktree", "reset"])
def test_dev_pr_recovers_interruption_without_losing_commits(python_exe, tmp_path, monkeypatch, boundary):
    repo, remote, _ = prepare(tmp_path, monkeypatch, branches=("develop",))
    head = git(repo, "rev-parse", "develop").stdout.strip()
    original_git, original_write = dev_pr.git, dev_pr.write_json
    fired = []

    def interrupt_git(where, *args, **kwargs):
        result = original_git(where, *args, **kwargs)
        if args[0] == boundary and not fired:
            fired.append(True)
            raise MDFError("模拟 Git 操作后中断", code="test_interrupted")
        return result

    def interrupt_write(path, state):
        original_write(path, state)
        if boundary == "record" and not fired:
            fired.append(True)
            raise MDFError("模拟记录后中断", code="test_interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(dev_pr, "git", interrupt_git)
        patch.setattr(dev_pr, "write_json", interrupt_write)
        assert mdf(python_exe, "dev-pr", "--repo", str(repo), "--slug", "rescue").returncode != 0
    assert fired
    result = payload(mdf(python_exe, "dev-pr", "--repo", str(repo)))["result"]
    assert result["source"] == "adhoc/rescue"
    assert git(repo, "rev-parse", "adhoc/rescue").stdout.strip() == head
    assert git(repo, "rev-parse", "develop").stdout == git(remote, "rev-parse", "develop").stdout


@pytest.mark.parametrize("dirty", ["tracked", "untracked", "merge"])
def test_dev_pr_preserves_dirty_develop(python_exe, tmp_path, monkeypatch, dirty):
    repo, remote, _ = prepare(tmp_path, monkeypatch, branches=("develop",))
    if dirty == "merge":
        git_dir = repo / ".git"
        (git_dir / "MERGE_HEAD").write_text(git(repo, "rev-parse", "HEAD").stdout)
    else:
        (repo / ("develop-local.txt" if dirty == "tracked" else "new.txt")).write_text("未提交\n")
    head, status = git(repo, "rev-parse", "HEAD").stdout, git(repo, "status", "--porcelain").stdout
    refs = git(remote, "show-ref").stdout
    result = mdf(python_exe, "dev-pr", "--repo", str(repo))
    assert result.returncode != 0 and "dirty_worktree" in result.stderr
    assert git(repo, "rev-parse", "HEAD").stdout == head
    assert git(repo, "status", "--porcelain").stdout == status
    assert git(remote, "show-ref").stdout == refs and not dev_pr.record_path(repo).exists()


@pytest.mark.parametrize("mixed", [False, True])
def test_trivial_policy_covers_entire_commit_series(python_exe, tmp_path, monkeypatch, mixed):
    repo, remote, _ = prepare(tmp_path, monkeypatch, branches=())
    git(repo, "checkout", "develop")
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() + '  trivial_paths: [".mdf/*", "docs/*"]\n')
    commit(repo)
    (repo / "docs/example.md").write_text("项目定义的 trivial\n")
    commit(repo)
    if mixed:
        (repo / "code.py").write_text("value = 1\n")
        commit(repo)
        git(repo, "revert", "--no-edit", "HEAD")
    preview = payload(mdf(python_exe, "sync", "--repo", str(repo)))
    assert bool(preview["pull_plan"]) == mixed
    if mixed:
        assert preview["pull_plan"]["develop"]["action"] == "dev_pr"
    else:
        assert payload(sync(python_exe, repo, pr=False))["trunks"]["develop"]["push"] == "updated"
        assert git(repo, "rev-parse", "develop").stdout == git(remote, "rev-parse", "develop").stdout


def test_dev_pr_no_pending_is_noop(python_exe, tmp_path, monkeypatch):
    repo, remote, _ = prepare(tmp_path, monkeypatch, branches=())
    before = git(repo, "show-ref").stdout
    assert payload(mdf(python_exe, "dev-pr", "--repo", str(repo)))["result"]["status"] == "no_pending_commits"
    assert git(repo, "show-ref").stdout == before
    assert not dev_pr.record_path(repo).exists()


def test_dev_pr_does_not_absorb_later_develop_commits(python_exe, tmp_path, monkeypatch):
    repo, _, _ = prepare(tmp_path, monkeypatch, branches=("develop",))
    first = payload(mdf(python_exe, "dev-pr", "--repo", str(repo)))["result"]
    (repo / "later.txt").write_text("下一批工作\n")
    commit(repo)
    later = git(repo, "rev-parse", "develop").stdout
    again = payload(sync(python_exe, repo))["pull_requests"]["develop"]
    assert again["source"] == first["source"]
    assert git(repo, "rev-parse", again["source"]).stdout.strip() == first["head"]
    assert git(repo, "rev-parse", "develop").stdout == later


@pytest.mark.parametrize("collision", ["branch", "worktree", "remote"])
def test_dev_pr_collision_never_resets_develop(python_exe, tmp_path, monkeypatch, collision):
    repo, remote, _ = prepare(tmp_path, monkeypatch, branches=("develop",))
    head = git(repo, "rev-parse", "develop").stdout
    if collision == "branch":
        git(repo, "branch", "adhoc/rescue", "master")
    elif collision == "remote":
        git(remote, "branch", "adhoc/rescue", "master")
    else:
        work = dev_pr.sibling_worktree(repo, "adhoc/rescue")
        work.mkdir(parents=True)
        (work / "keep.txt").write_text("已有文件\n")
    result = mdf(python_exe, "dev-pr", "--repo", str(repo), "--slug", "rescue")
    assert result.returncode != 0 and "collision" in result.stderr
    assert git(repo, "rev-parse", "develop").stdout == head


def test_dev_pr_handles_develop_in_another_worktree(python_exe, tmp_path, monkeypatch):
    repo, remote, _ = prepare(tmp_path, monkeypatch, branches=("develop",))
    git(repo, "checkout", "master")
    develop = tmp_path / "develop-work"
    git(repo, "worktree", "add", str(develop), "develop")
    state = payload(mdf(python_exe, "dev-pr", "--repo", str(repo)))["result"]
    assert git(develop, "rev-parse", "HEAD").stdout == git(remote, "rev-parse", "develop").stdout
    assert (Path(state["worktree"]) / "develop-local.txt").exists()
    assert git(repo, "branch", "--show-current").stdout.strip() == "master"


def test_default_trivial_and_explicit_empty_override(python_exe, tmp_path, monkeypatch):
    repo, _, _ = prepare(tmp_path, monkeypatch, branches=())
    git(repo, "checkout", "develop")
    (repo / "AGENTS.md").write_text("项目维护\n")
    commit(repo)
    assert not payload(mdf(python_exe, "sync", "--repo", str(repo)))["pull_plan"]
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text() + "  trivial_paths: []\n")
    commit(repo)
    assert payload(mdf(python_exe, "sync", "--repo", str(repo)))["pull_plan"]["develop"]["action"] == "dev_pr"


def test_dev_pr_rejects_changed_confirmed_tip(tmp_path, monkeypatch):
    repo, remote, _ = prepare(tmp_path, monkeypatch, branches=("develop",))
    old = git(repo, "rev-parse", "develop").stdout.strip()
    (repo / "later.txt").write_text("确认之后的新工作\n")
    commit(repo)
    new = git(repo, "rev-parse", "develop").stdout.strip()
    with pytest.raises(MDFError, match="已确认计划"):
        dev_pr.prepare(repo, expected_head=old)
    assert git(repo, "rev-parse", "develop").stdout.strip() == new
    assert not dev_pr.record_path(repo).exists()


def test_enabling_pr_locally_cannot_direct_push_nontrivial_series(python_exe, tmp_path, monkeypatch):
    repo, remote, _ = prepare(tmp_path, monkeypatch, branches=("develop",))
    git(remote, "update-ref", "refs/heads/develop", "develop^")
    preview = payload(mdf(python_exe, "sync", "--repo", str(repo)))
    assert preview["pull_plan"]["develop"]["action"] == "dev_pr"

    first = payload(mdf(python_exe, "dev-pr", "--repo", str(repo)))["result"]
    again = payload(mdf(python_exe, "dev-pr", "--repo", str(repo)))["result"]
    assert first["source"] == again["source"]
