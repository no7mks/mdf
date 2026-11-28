"""历史整理保持已验收内容，映射 SHA 后直接发布。"""
import json
from pathlib import Path

import pytest

from mdf_test_support import git, mdf, payload, run
from support_delivery import commit, seed_consolidation
from support_github_flow import error_of
from test_catchup import advance, complete, prepared
from mdf_core.lifecycle.catchup import state_path
from mdf_core.workspace.squash import check
from squash_execute import execute


def squashed(python_exe, tmp_path, monkeypatch):
    _, remote, work, peer = prepared(python_exe, tmp_path, monkeypatch)
    floor = git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "src/local.py").write_text("local = True\n")
    commit(work)
    synced = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    done = payload(complete(python_exe, work, synced["head"]))
    seed_consolidation(work, mark=True)
    plan = check(work)
    assert plan["floor"] == floor
    plan.update(start_commit=floor, segments=[{"tip": plan["old_tip"], "message": "fix: 整理本地交付"}])
    return remote, work, peer, floor, done["head"], plan


def test_squash_preserves_acceptance_and_publishes(python_exe, tmp_path, monkeypatch):
    remote, work, _, _, old_base, plan = squashed(python_exe, tmp_path, monkeypatch)
    result = execute(work.resolve(), plan, False, [])
    verified = execute(work.resolve(), plan, True, [])
    assert verified["tree_equal"] and verified["clean"] and verified["start_is_ancestor"]
    assert run(["git", "merge-base", "--is-ancestor", old_base, "HEAD"], cwd=work).returncode == 1
    path = state_path(work, "release/1.3.0")
    state = json.loads(path.read_text())
    assert state["completed_head"] == result["head"]
    assert state["squash_mapping"]["fields"]["completed_head"]["before"] == old_base
    before = path.read_text()
    execute(work.resolve(), plan, True, [])
    assert path.read_text() == before
    published = payload(mdf(python_exe, "publish", "--repo", str(work)))
    tag = git(remote, "rev-parse", "v1.3.0").stdout
    assert published["release_head"] == result["head"]
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == published["release_head"]
    payload(mdf(python_exe, "publish", "--repo", str(work)))
    assert git(remote, "rev-parse", "v1.3.0").stdout == tag


def test_new_content_and_remote_advance_still_require_validation(python_exe, tmp_path, monkeypatch):
    remote, work, peer, _, _, plan = squashed(python_exe, tmp_path, monkeypatch)
    result = execute(work.resolve(), plan, False, [])
    (work / "src/after.py").write_text("after = True\n")
    commit(work)
    incoming = advance(peer)
    assert error_of(mdf(python_exe, "publish", "--repo", str(work)))["error"] == "consolidation_required"
    recovered = payload(mdf(python_exe, "catch-up", "--repo", str(work)))
    assert recovered["plan"]["base"] == result["head"]
    assert {"src/after.py", "src/service.py"} <= set(recovered["plan"]["review"]["paths"])
    assert "src/local.py" not in recovered["plan"]["review"]["paths"]
    assert recovered["plan"]["verify"]["action"] == "smart"
    git(work, "merge-base", "--is-ancestor", incoming, "HEAD")
    assert git(remote, "rev-parse", "release/1.3.0").stdout.strip() == incoming


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("partial", [False, True])
def test_verify_only_repairs_interrupted_mapping(python_exe, tmp_path, monkeypatch, pending, partial):
    from mdf_core.lifecycle import squash_state
    from mdf_core.lifecycle.consolidation import record_path
    remote, work, _, _, _, plan = squashed(python_exe, tmp_path, monkeypatch)
    def interrupt(*args):
        raise RuntimeError("映射写入前中断")
    with monkeypatch.context() as patch:
        patch.setattr(squash_state, "remap", interrupt)
        with pytest.raises(RuntimeError, match="映射写入前中断"):
            execute(work.resolve(), plan, False, [])
    if pending:
        # 故障入口在 build_plan 前已移除 completed_head 并标记 consolidation pending。
        path = state_path(work, "release/1.3.0")
        state = json.loads(path.read_text())
        state["base"] = state.pop("completed_head")
        path.write_text(json.dumps(state))
        path = record_path(work, "release/1.3.0")
        state = json.loads(path.read_text())
        path.write_text(json.dumps({**state, "pending": True}))
    if partial:
        original = squash_state.write_json
        def interrupt_write(path, state):
            original(path, state)
            if path == state_path(work, "release/1.3.0"):
                raise RuntimeError("catch-up 写入后中断")
        with monkeypatch.context() as patch:
            patch.setattr(squash_state, "write_json", interrupt_write)
            with pytest.raises(RuntimeError, match="catch-up 写入后中断"):
                execute(work.resolve(), plan, True, [])
    result = execute(work.resolve(), plan, True, [])
    published = payload(mdf(python_exe, "publish", "--repo", str(work)))
    assert published["release_head"] == result["head"]
    assert git(remote, "rev-parse", "v1.3.0^{commit}").stdout.strip() == result["head"]


def test_failed_tree_verification_never_updates_acceptance(python_exe, tmp_path, monkeypatch):
    _, work, _, _, _, plan = squashed(python_exe, tmp_path, monkeypatch)
    path = state_path(work, "release/1.3.0")
    before = path.read_text()
    hooks = Path(git(work, "rev-parse", "--git-path", "hooks").stdout.strip())
    hooks.mkdir(exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nprintf 'extra = True\\n' > src/extra.py\ngit add src/extra.py\n")
    hook.chmod(0o755)
    with pytest.raises(ValueError, match="tree"):
        execute(work.resolve(), plan, False, [])
    assert path.read_text() == before
    with pytest.raises(ValueError, match="tree"):
        execute(work.resolve(), plan, True, [])
    assert path.read_text() == before


def test_repeated_segment_tree_maps_tip_to_last_segment(python_exe, tmp_path, monkeypatch):
    from mdf_core.lifecycle.consolidation import record_path
    _, work, _, floor, _, _ = squashed(python_exe, tmp_path, monkeypatch)
    first = git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "src/local.py").write_text("local = False\n")
    commit(work)
    second = git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "src/local.py").write_text("local = True\n")
    commit(work)
    last = git(work, "rev-parse", "HEAD").stdout.strip()
    # 原历史的三段均已验收；两端 tree 相同，中间段不同。
    path = state_path(work, "release/1.3.0")
    state = json.loads(path.read_text())
    path.write_text(json.dumps({**state, "completed_head": last}))
    path = record_path(work, "release/1.3.0")
    path.write_text(json.dumps({"head": last}))
    from mdf_core.lifecycle.target_integration import state_path as integration_path
    integration_path(work, "release/1.3.0").write_text(json.dumps({"base": last}))
    plan = check(work)
    assert plan["floor"] == floor
    plan.update(start_commit=floor, segments=[{"tip": tip, "message": f"test: 段 {i}"}
                                            for i, tip in enumerate((first, second, last))])
    result = execute(work.resolve(), plan, False, [])
    assert json.loads(state_path(work, "release/1.3.0").read_text())["completed_head"] == result["head"]
    assert result["commits"][0] != result["head"]
    assert git(work, "rev-parse", result["commits"][0] + "^{tree}").stdout == git(work, "rev-parse", "HEAD^{tree}").stdout
    execute(work.resolve(), plan, True, [])
    payload(mdf(python_exe, "publish", "--repo", str(work)))
