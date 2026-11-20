"""手动分支只以 Change 收口；不创建或修补 delivery/objectives。"""
import json

import pytest

from mdf_test_support import git, mdf, payload
from mdf_test_support import finish_delivery
from support_delivery import commit, local_repo, write_change


def manual_work(tmp_path, source="chore/readme", *, linked=False):
    repo = local_repo(tmp_path)
    git(repo, "checkout", "develop")
    if linked:
        work = tmp_path / "manual-work"
        git(repo, "worktree", "add", "-b", source, str(work), "develop")
    else:
        work = repo
        git(work, "checkout", "-b", source)
    (work / "manual.txt").write_text("本次工作\n")
    commit(work)
    return repo, work


@pytest.mark.parametrize("source", ["scratch", "chore/readme", "adhoc/readme", "中文", "adhoc/中文"])
@pytest.mark.parametrize("linked", [False, True])
def test_change_only_finish_preserves_real_branch_and_worktree(python_exe, tmp_path, source, linked):
    repo, work = manual_work(tmp_path, source, linked=linked)
    status = payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]
    root = write_change(work, source, status["slug"])
    commit(work)
    head = git(work, "rev-parse", "HEAD").stdout.strip()
    result = payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work)))
    assert result["completed"] and result["source"] == source and not result["pushed"]
    assert git(repo, "rev-parse", "develop^2").stdout.strip() == head
    assert source not in git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").stdout.splitlines()
    assert not (root / "delivery.json").exists() and not (root / "objectives.md").exists()
    assert work.is_dir()
    if linked:
        assert git(work, "rev-parse", "HEAD").stdout.strip() == head
        assert not git(work, "branch", "--show-current").stdout.strip()
    else:
        assert git(work, "branch", "--show-current").stdout.strip() == "develop"
    finished = payload(mdf(python_exe, "adhoc-status", "--repo", str(work), "--source", source))["result"]
    assert finished["completed"] and finished["next_step"] is None
    repeated = payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work), "--source", source))
    assert repeated["completed"] and repeated["merge_commit"] == result["merge_commit"]


def test_change_only_smart_uses_resolved_material_directory(python_exe, tmp_path):
    _, work = manual_work(tmp_path)
    root = write_change(work, "chore/readme", "separate-material-name")
    commit(work)
    result = payload(mdf(python_exe, "verify", "smart", "--repo", str(work), "--module", "default"))["result"]
    assert result["kind"] == "adhoc" and result["all_passed"]
    assert json.loads((root / "verification-report.json").read_text()) == result
    assert not (work / "changes/unreleased/chore-readme").exists()


def test_material_collision_does_not_reuse_inherited_delivery(python_exe, tmp_path):
    _, work = manual_work(tmp_path)
    inherited = work / "changes/unreleased/chore-readme"
    inherited.mkdir(parents=True)
    (inherited / "delivery.json").write_text(json.dumps({"branch": "feature/other-work"}))
    commit(work)
    before = (inherited / "delivery.json").read_text()
    result = payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]
    assert result["material_mode"] == "change" and result["slug"].startswith("chore-readme-")
    payload(mdf(python_exe, "verify", "smart", "--repo", str(work), "--module", "default"))
    assert payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]["slug"] == result["slug"]
    root = write_change(work, "chore/readme", result["slug"])
    commit(work)
    payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work)))
    assert (inherited / "delivery.json").read_text() == before
    assert root.is_dir()


@pytest.mark.parametrize("material", ["objectives.md", "delivery.json"])
def test_broken_ledger_never_falls_back_to_change_only(python_exe, tmp_path, material):
    _, work = manual_work(tmp_path)
    root = write_change(work, "chore/readme", "chore-readme")
    (root / material).write_text("broken")
    commit(work)
    result = finish_delivery(python_exe, "finish-gitflow", "--repo", str(work))
    assert result.returncode != 0 and "invalid_delivery" in result.stderr
    assert git(work, "branch", "--show-current").stdout.strip() == "chore/readme"


@pytest.mark.parametrize("source", ["qa/feature/example", "dev/2/bugfix/bug-AB12", "codex/backmerge/1.2.3"])
def test_internal_workflow_cannot_be_finished_as_adhoc(python_exe, tmp_path, source):
    _, work = manual_work(tmp_path, source)
    result = finish_delivery(python_exe, "finish-gitflow", "--repo", str(work))
    assert result.returncode != 0 and "stage_branch" in result.stderr


def test_empty_manual_branch_does_not_create_change_or_delete_source(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    git(repo, "checkout", "-b", "scratch", "develop")
    before = git(repo, "status", "--porcelain").stdout
    result = finish_delivery(python_exe, "finish-gitflow", "--repo", str(repo))
    assert result.returncode != 0 and "no_pending_commits" in result.stderr
    assert git(repo, "branch", "--show-current").stdout.strip() == "scratch"
    assert git(repo, "status", "--porcelain").stdout == before


def test_local_finish_resumes_after_merge_without_repeating_it(python_exe, tmp_path, monkeypatch):
    repo, work = manual_work(tmp_path, linked=True)
    write_change(work, "chore/readme", "chore-readme")
    commit(work)
    from mdf_core.lifecycle import pull_finish
    from mdf_core.foundation.errors import MDFError
    original = pull_finish.cleanup

    def interrupt(*_):
        raise MDFError("模拟清理中断", code="test_interrupted")

    monkeypatch.setattr(pull_finish, "cleanup", interrupt)
    failed = finish_delivery(python_exe, "finish-gitflow", "--repo", str(work))
    assert failed.returncode != 0 and "test_interrupted" in failed.stderr
    merged = git(repo, "rev-parse", "develop").stdout.strip()
    monkeypatch.setattr(pull_finish, "cleanup", original)
    result = payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work), "--source", "chore/readme"))
    assert result["completed"] and result["merge_commit"] == merged
    assert git(repo, "rev-parse", "develop").stdout.strip() == merged
    again = payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(work), "--source", "chore/readme"))
    assert again["merge_commit"] == merged


def test_fixed_range_survives_target_integration_and_protects_squash(python_exe, tmp_path):
    repo, work = manual_work(tmp_path, linked=True)
    original = payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]
    root = write_change(work, "chore/readme", original["slug"])
    change = root / "CHANGE.md"
    fixed = original["range"]
    change.write_text(change.read_text().replace("evidence:\n", "evidence:\n  range:\n" + "".join(
        f"    {key}: {value}\n" for key, value in fixed.items())))
    commit(work)
    (repo / "target.txt").write_text("目标前进\n")
    commit(repo)
    git(work, "merge", "--no-ff", "develop", "-m", "test: 集成目标")
    status = payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]
    assert status["range"]["base"] == fixed["base"]
    assert status["range"]["target_head"] != fixed["target_head"]
    assert "manual.txt" in status["paths"]
    from mdf_core.workspace.squash import inspect
    plan = inspect(work, refresh=False)
    history = git(work, "rev-list", plan["floor"]).stdout.splitlines()
    assert fixed["source_head"] in history


def test_local_primary_detaches_when_develop_is_occupied_elsewhere(python_exe, tmp_path):
    repo, _ = manual_work(tmp_path)
    target = tmp_path / "develop-work"
    git(repo, "worktree", "add", str(target), "develop")
    write_change(repo, "chore/readme", "chore-readme")
    commit(repo)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    result = payload(finish_delivery(python_exe, "finish-gitflow", "--repo", str(repo)))
    assert result["completed"] and repo.is_dir()
    assert not git(repo, "branch", "--show-current").stdout.strip()
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == head
    assert git(target, "branch", "--show-current").stdout.strip() == "develop"


@pytest.mark.parametrize("status", ["open", "rejected"])
def test_change_only_finish_rejects_unfixed_bug_before_merge(python_exe, tmp_path, status):
    repo, work = manual_work(tmp_path, linked=True)
    root = write_change(work, "chore/readme", "chore-readme")
    bug = work / "docs/bugs/bug-0001-example.md"
    bug.parent.mkdir(parents=True, exist_ok=True)
    bug.write_text(f"---\nid: bug-0001\ntype: bug\nstatus: {status}\n---\n")
    change = root / "CHANGE.md"
    change.write_text(change.read_text().replace("fixed: []", "fixed: [bug-0001]"))
    commit(work)
    target = git(repo, "rev-parse", "develop").stdout.strip()
    result = finish_delivery(python_exe, "finish-gitflow", "--repo", str(work))
    assert result.returncode != 0 and "change.fixed_status" in result.stderr
    assert git(repo, "rev-parse", "develop").stdout.strip() == target
    assert git(work, "branch", "--show-current").stdout.strip() == "chore/readme"
