"""材料提交只包含 consolidate 拥有的路径。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import start_repo, commit, write_change
from support_github_flow import error_of


def test_consolidate_preserves_concurrent_unrelated_changes(python_exe, tmp_path, monkeypatch):
    from mdf_core.lifecycle.manual import STEPS
    from mdf_core.inspection import doctor
    repo, _ = start_repo(tmp_path)
    obj = tmp_path / "manual.md"
    obj.write_text("# 目标\n\n" + "".join(f"- [{'x' if name == 'start' else ' '}] {name}\n" for name in STEPS))
    started = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature", "--manual",
                          "--name", "material-test", "--objectives-file", str(obj)))
    work = Path(started["worktree"])
    root = write_change(work, started["branch"], "material-test")
    change = root / "CHANGE.md"
    change.write_text(change.read_text().replace("change_kind: fix", "change_kind: feature"))
    objective = root / "objectives.md"
    objective.write_text(objective.read_text().replace("[ ]", "[x]").replace("[x] consolidate", "[ ] consolidate"))
    commit(work)
    before = git(work, "rev-parse", "HEAD").stdout
    original = doctor.collect_findings

    def concurrent(repo, **kwargs):
        findings = original(repo, **kwargs)
        (repo / "other-work.txt").write_text("其他写入者的内容\n")
        return findings

    monkeypatch.setattr(doctor, "collect_findings", concurrent)
    failed = mdf(python_exe, "consolidate", "--repo", str(work))
    assert error_of(failed)["error"] == "unrelated_staged_changes"
    assert git(work, "rev-parse", "HEAD").stdout == before
    assert (work / "other-work.txt").read_text() == "其他写入者的内容\n"
    assert not git(work, "diff", "--cached", "--name-only").stdout


@pytest.mark.parametrize("command", ["catch-up", "consolidate", "incremental-integration"])
def test_delivery_stages_require_owner_worktree(python_exe, tmp_path, command):
    from support_delivery import setup_delivery, sync_roles
    owner, _root, _remote = setup_delivery(python_exe, tmp_path)
    qa, _dev = sync_roles(python_exe, owner)
    before = git(qa, "rev-parse", "HEAD").stdout
    assert error_of(mdf(python_exe, command, "--repo", str(qa)))["error"] == "stage_branch"
    assert git(qa, "rev-parse", "HEAD").stdout == before
    assert not git(qa, "status", "--porcelain").stdout
