"""catch-up 先验证计划；同步发生后继续保留未验收保护。"""
import json

import pytest

from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.catchup import state_path
from mdf_core.lifecycle.consolidation import record_path
from mdf_test_support import git, mdf, payload
from support_delivery import commit, seed_consolidation
from support_github_flow import error_of
from test_catchup import advance, complete, prepared
from test_catchup_squash import squashed
from squash_execute import execute


def completed(python_exe, tmp_path, monkeypatch):
    _, remote, work, peer = prepared(python_exe, tmp_path, monkeypatch)
    ready = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    payload(complete(python_exe, work, ready["head"]))
    seed_consolidation(work, mark=True)
    return remote, work, peer


@pytest.mark.parametrize("failure", ["base", "modules"])
def test_invalid_plan_preserves_completed_state(python_exe, tmp_path, monkeypatch, failure):
    _, work, peer = completed(python_exe, tmp_path, monkeypatch)
    path = state_path(work, "release/1.3.0")
    if failure == "base":
        state = json.loads(path.read_text())
        # 远端 commit 尚未合入本地，不能拿它冒充已验收的本地端点。
        state["completed_head"] = advance(peer)
        path.write_text(json.dumps(state))
    else:
        (work / ".mdf/modules.yaml").write_text("modules: []\n")
        commit(work)
    consolidate = record_path(work, "release/1.3.0")
    before = {p: p.read_bytes() for p in (path, consolidate)}
    head = git(work, "rev-parse", "HEAD").stdout
    result = mdf(python_exe, "catch-up", "--repo", str(work))
    assert result.returncode != 0
    if failure == "base":
        assert error_of(result)["error"] == "invalid_integration_base"
    assert {p: p.read_bytes() for p in before} == before
    assert git(work, "rev-parse", "HEAD").stdout == head
    assert not git(work, "status", "--porcelain").stdout


def test_plan_failure_after_remote_merge_keeps_pending(python_exe, tmp_path, monkeypatch):
    from mdf_core.lifecycle import incremental_plan

    _, work, peer = completed(python_exe, tmp_path, monkeypatch)
    before = json.loads(state_path(work, "release/1.3.0").read_text())["completed_head"]
    incoming = advance(peer)
    original = incremental_plan.build_plan

    def fail_after_merge(repo, *args, **kwargs):
        if (repo / "src/service.py").read_text() == "remote = True\n":
            raise MDFError("同步后计划中断", code="test_plan_interrupted")
        return original(repo, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(incremental_plan, "build_plan", fail_after_merge)
        failed = mdf(python_exe, "catch-up", "--repo", str(work))
    assert error_of(failed)["error"] == "test_plan_interrupted"
    git(work, "merge-base", "--is-ancestor", incoming, "HEAD")
    state = json.loads(state_path(work, "release/1.3.0").read_text())
    assert "completed_head" not in state and state["base"] == before
    assert json.loads(record_path(work, "release/1.3.0").read_text())["pending"] is True
    assert error_of(mdf(python_exe, "publish", "--repo", str(work)))["error"] == "catchup_required"
    resumed = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    assert resumed["plan"]["base"] == before
    assert "src/service.py" in resumed["plan"]["review"]["paths"]
    assert resumed["plan"]["verify"]["action"] == "smart"
    payload(complete(python_exe, work, resumed["head"]))


@pytest.mark.parametrize("change", ["local", "remote"])
def test_squash_new_content_requires_its_own_validation(python_exe, tmp_path, monkeypatch, change):
    _, work, peer, _, _, plan = squashed(python_exe, tmp_path, monkeypatch)
    result = execute(work.resolve(), plan, False, [])
    if change == "local":
        (work / "src/after.py").write_text("after = True\n")
        commit(work)
        expected = "src/after.py"
    else:
        advance(peer)
        expected = "src/service.py"
    assert mdf(python_exe, "publish", "--repo", str(work)).returncode != 0
    resumed = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    assert resumed["plan"]["base"] == result["head"]
    assert expected in resumed["plan"]["review"]["paths"]
    assert "src/local.py" not in resumed["plan"]["review"]["paths"]
    assert resumed["plan"]["verify"]["action"] == "smart"


def test_linked_worktree_shares_receipts_but_new_clone_does_not(python_exe, tmp_path, monkeypatch):
    _, work, _ = completed(python_exe, tmp_path, monkeypatch)
    source = "release/1.3.0"
    linked, cloned = tmp_path / "linked", tmp_path / "cloned"
    git(work, "worktree", "add", "--detach", str(linked), "HEAD")
    git(tmp_path, "clone", "--branch", source, str(work), str(cloned))
    assert state_path(linked, source) == state_path(work, source)
    assert record_path(linked, source) == record_path(work, source)
    assert not state_path(cloned, source).exists()
    assert not record_path(cloned, source).exists()
    assert error_of(mdf(python_exe, "publish", "--repo", str(cloned)))["error"] == "consolidation_required"
    result = payload(mdf(python_exe, "catch-up", "--repo", str(cloned)))
    assert result["completed"] is False
    assert "completed_head" not in json.loads(state_path(cloned, source).read_text())


def test_interrupted_squash_rejects_stale_base_without_erasing_receipts(python_exe, tmp_path, monkeypatch):
    from mdf_core.lifecycle import squash_state

    _, work, _, _, _, plan = squashed(python_exe, tmp_path, monkeypatch)

    def interrupt(*args):
        raise RuntimeError("映射前中断")

    with monkeypatch.context() as patch:
        patch.setattr(squash_state, "remap", interrupt)
        with pytest.raises(RuntimeError, match="映射前中断"):
            execute(work.resolve(), plan, False, [])
    paths = (state_path(work, "release/1.3.0"), record_path(work, "release/1.3.0"))
    before = [p.read_bytes() for p in paths]
    assert error_of(mdf(python_exe, "catch-up", "--repo", str(work)))["error"] == "invalid_integration_base"
    assert [p.read_bytes() for p in paths] == before
    result = execute(work.resolve(), plan, True, [])
    published = payload(mdf(python_exe, "publish", "--repo", str(work)))
    assert published["release_head"] == result["head"]
