"""无账本 adhoc 的平台收口；离线平台与真实 bare Git remote。"""
import pytest

from mdf_test_support import git, mdf, payload
from support_delivery import commit
from support_pull import prepare, squash_pending
from test_untracked_adhoc import write_change


def prepare_change_only(python_exe, tmp_path, monkeypatch, source="chore/docs"):
    repo, remote, work, platform = prepare(python_exe, tmp_path, monkeypatch, "adhoc")
    root = work / "changes/unreleased/service-health"
    (root / "delivery.json").unlink()
    (root / "objectives.md").unlink()
    git(work, "branch", "-m", source)
    write_change(work, source, root.name)
    commit(work)
    squash_pending(work)
    return repo, remote, work, platform


@pytest.mark.parametrize("source", ["chore/docs", "adhoc/service-health", "scratch", "foo.json/bar"])
def test_change_only_pr_and_closeout_keep_ci_independent(python_exe, tmp_path, monkeypatch, source):
    repo, remote, work, platform = prepare_change_only(python_exe, tmp_path, monkeypatch, source)
    initial = payload(mdf(python_exe, "pr", "--repo", str(work)))
    assert initial["status"] == "waiting_for_merge" and initial["source"] == source
    assert platform.pulls[0]["target"] == "develop"
    not_merged = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    assert not_merged.returncode != 0 and "pr_not_merged" in not_merged.stderr
    merged = platform.merge(1, tmp_path)
    result = payload(mdf(python_exe, "pr", "--repo", str(work)))
    assert result["completed"] and result["merge_commit"] == merged
    assert git(work, "branch", "--show-current").stdout.strip() == source
    finished = payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo), "--source", source))
    assert finished["completed"] and finished["remote_deleted"] and finished["merge_commit"] == merged
    assert not git(work, "branch", "--show-current").stdout.strip()
    assert source not in git(remote, "for-each-ref", "--format=%(refname:short)", "refs/heads").stdout.splitlines()
    root = work / "changes/unreleased/service-health"
    assert not (root / "delivery.json").exists() and not (root / "objectives.md").exists()
    state = payload(mdf(python_exe, "adhoc-status", "--repo", str(work), "--source", source))["result"]
    assert state["completed"] and state["material_mode"] == "change"


def test_closeout_adopts_actual_external_merge_without_pr_record(python_exe, tmp_path, monkeypatch):
    repo, remote, work, platform = prepare_change_only(python_exe, tmp_path, monkeypatch)
    source = "chore/docs"
    git(work, "push", "origin", source)
    platform.create(source, "develop", "test: 直接创建 PR", "")
    merged = platform.merge(1, tmp_path)
    result = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert result["completed"] and result["remote_deleted"] and result["merge_commit"] == merged
    assert len(platform.pulls) == 1
    assert git(remote, "rev-parse", "develop").stdout.strip() == merged


def test_change_only_pr_cannot_bypass_squash_or_invalid_change(python_exe, tmp_path, monkeypatch):
    _, _, work, platform = prepare_change_only(python_exe, tmp_path, monkeypatch)
    for index in range(2):
        (work / "extra.txt").write_text(str(index))
        commit(work)
    result = mdf(python_exe, "pr", "--repo", str(work))
    assert result.returncode != 0 and "squash_required" in result.stderr
    assert platform.pulls == []
    change = work / "changes/unreleased/service-health/CHANGE.md"
    change.write_text(change.read_text().replace("proposals: []", "proposals: [prp-0001]"))
    commit(work)
    result = mdf(python_exe, "pr", "--repo", str(work))
    assert result.returncode != 0 and "invalid_change" in result.stderr
    assert platform.pulls == []


def test_external_merge_is_verified_before_creating_recovery_record(python_exe, tmp_path, monkeypatch):
    repo, _, work, platform = prepare_change_only(python_exe, tmp_path, monkeypatch)
    git(work, "push", "origin", "chore/docs")
    platform.create("chore/docs", "develop", "test: 外部 PR", "")
    platform.pulls[0].update(state="merged", merge_commit=git(repo, "rev-parse", "develop").stdout.strip())
    from mdf_core.lifecycle.publish import state_path
    result = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    assert result.returncode != 0 and "invalid_pull_merge" in result.stderr
    assert not state_path(repo, "chore/docs").exists()
    assert git(work, "branch", "--show-current").stdout.strip() == "chore/docs"
