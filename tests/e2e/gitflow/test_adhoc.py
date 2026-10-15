"""Adhoc 独立工作区、smart 证据与本地收口。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import local_repo, commit
from mdf_core.adhoc import STEPS


def start_adhoc(python_exe, tmp_path, *extra):
    repo = local_repo(tmp_path)
    git(repo, "checkout", "develop")
    result = mdf(python_exe, "start", "--repo", str(repo), "--kind", "adhoc",
                 "--name", "update-readme", "--work", "更新配置说明并保留使用示例", *extra)
    return repo, result


def write_change(root, *, proposals="[]"):
    (root / "CHANGE.md").write_text(
        "---\nchange_kind: adhoc\nsource_branch: adhoc/update-readme\n"
        f"proposals: {proposals}\nfixed: []\nclosed: []\ndeferred: []\nadrs: []\n"
        "release_notes: none\nbreaking: false\nevidence:\n"
        "  tests: []\n  commands: [\"true\"]\n  artifacts: []\n---\n\n"
        "# Change\n\n## 结果\n\n已更新说明。\n\n"
        "## 已更新的当前文档\n\n- README.md\n\n## 已知偏差\n\n无。\n"
    )


def test_adhoc_start_keeps_primary_and_trunks_unchanged(python_exe, tmp_path):
    repo, result = start_adhoc(python_exe, tmp_path)
    data = payload(result)
    work = Path(data["worktree"])
    root = work / "changes/unreleased/update-readme"
    identity = json.loads((root / "delivery.json").read_text())
    assert data["branch"] == "adhoc/update-readme" and data["base"] == "develop"
    assert work == repo.parent / "repo-worktrees/adhoc/update-readme"
    assert data["roles"] == {"qa": [], "dev": []}
    assert tuple(data["roster"][key] for key in ("qa", "dev", "reviewers")) == (0, 0, 1)
    assert identity["needs_design"] is False
    assert identity["work"] == "更新配置说明并保留使用示例"
    assert not {"proposal", "bug", "manual"} & identity.keys()
    assert re.findall(r"^- \[ \] (.+)$", (root / "objectives.md").read_text(), re.M) == list(STEPS)
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert git(repo, "rev-parse", "develop").stdout.strip() == data["start_commit"]
    assert git(repo, "rev-parse", "master").stdout.strip() == data["start_commit"]
    status = payload(mdf(python_exe, "delivery", "status", "--repo", str(work)))["result"]
    assert status["worktrees"]["owner"]["path"] == str(work)
    assert not git(work, "status", "--porcelain").stdout.strip()
    status = payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]
    assert not status["completed"] and status["next_step"] == "工作"
    assert status["delivery"]["work"] == identity["work"]


@pytest.mark.parametrize("extra,error", [
    (["--proposal", "prp-001"], "invalid_adhoc"),
    (["--bug", BUG_ID], "invalid_adhoc"),
    (["--version", "1.3.0"], "invalid_adhoc"),
    (["--objectives-file", "unused.md"], "invalid_adhoc"),
    (["--roster", "min-tdd"], "invalid_adhoc"),
    (["--reviewers", "2"], "invalid_adhoc"),
    (["--manual"], "invalid_manual"),
    (["--name", ""], "invalid_slug"),
    (["--work", ""], "missing_adhoc_work"),
])
def test_adhoc_rejects_invalid_input_without_creating_worktree(python_exe, tmp_path, extra, error):
    repo, result = start_adhoc(python_exe, tmp_path, *extra)
    assert result.returncode != 0 and error in result.stderr
    assert not git(repo, "for-each-ref", "refs/heads/adhoc/").stdout
    assert len(git(repo, "worktree", "list", "--porcelain").stdout.split("worktree ")) == 2


def test_adhoc_finish_requires_completed_work_and_preserves_prp(python_exe, tmp_path):
    repo, result = start_adhoc(python_exe, tmp_path)
    work = Path(payload(result)["worktree"])
    root = work / "changes/unreleased/update-readme"
    before = git(repo, "show", f"develop:docs/proposals/{PRP_NAME}").stdout
    write_change(root)
    commit(work)
    failed = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    assert failed.returncode != 0 and "adhoc_work_pending" in failed.stderr
    assert git(work, "branch", "--show-current").stdout.strip() == "adhoc/update-readme"
    objectives = root / "objectives.md"
    objectives.write_text(objectives.read_text().replace("[ ]", "[x]"))
    commit(work)
    write_change(root, proposals="[prp-001]")
    commit(work)
    from mdf_core.validate_changes import validate_changes
    findings = []
    validate_changes(work, findings)
    assert any(item.code == "change.proposals" for item in findings)
    failed = mdf(python_exe, "finish-gitflow", "--repo", str(work))
    assert failed.returncode != 0 and "invalid_change" in failed.stderr
    write_change(root)
    commit(work)
    source = git(work, "rev-parse", "HEAD").stdout.strip()
    status = payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]
    assert not status["completed"] and status["next_step"] == "close-out"
    result = payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert result["targets"] == ["develop"] and result["pushed"] is False
    assert result["retained_worktree"] == str(work) and work.is_dir()
    assert not git(work, "branch", "--show-current").stdout.strip()
    assert not git(repo, "for-each-ref", "refs/heads/adhoc/").stdout
    assert len(git(repo, "rev-list", "--parents", "-n", "1", "develop").stdout.split()) == 3
    assert git(repo, "rev-parse", "develop^2").stdout.strip() == source
    assert git(repo, "show", f"develop:docs/proposals/{PRP_NAME}").stdout == before
    status = payload(mdf(python_exe, "adhoc-status", "--repo", str(work), "--slug", "update-readme"))["result"]
    assert status["completed"] and status["next_step"] is None
    assert status["head"] == source and status["merge_commit"] == git(repo, "rev-parse", "develop").stdout.strip()
    findings = []
    validate_changes(work, findings)
    assert findings == []


def test_adhoc_smart_persists_success_and_failure_without_smoke(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    patch_module_command(repo, "smoke", lambda _: "exit 99")
    commit(repo)
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "adhoc",
                       "--name", "check", "--work", "核对 smart 不执行 smoke"))
    work = Path(data["worktree"])
    report = work / "changes/unreleased/check/verification-report.json"
    passed = payload(mdf(python_exe, "verify", "smart", "--repo", str(work), "--module", "default"))["result"]
    assert passed["scope"] == "smart" and passed["kind"] == "adhoc" and passed["all_passed"]
    assert json.loads(report.read_text()) == passed
    assert {item["entry"] for item in passed["results"]} == {"lint", "build", "quick"}
    patch_module_command(work, "quick", lambda _: "exit 42")
    failed = mdf(python_exe, "verify", "smart", "--repo", str(work), "--module", "default")
    assert failed.returncode != 0 and "verify_command_failed" in failed.stderr
    assert json.loads(report.read_text())["all_passed"] is False


@pytest.mark.parametrize("patch", [
    {"work": ""}, {"work": None}, {"needs_design": True},
    {"proposal": "prp-001"}, {"manual": True}, {"slug": "another-task"},
])
def test_adhoc_status_rejects_changed_identity_without_repairing_it(python_exe, tmp_path, patch):
    _, result = start_adhoc(python_exe, tmp_path)
    work = Path(payload(result)["worktree"])
    path = work / "changes/unreleased/update-readme/delivery.json"
    data = {**json.loads(path.read_text()), **patch}
    path.write_text(json.dumps(data))
    before = git(work, "status", "--porcelain").stdout
    result = mdf(python_exe, "adhoc-status", "--repo", str(work))
    assert result.returncode != 0 and "invalid_delivery" in result.stderr
    assert json.loads(path.read_text()) == data
    assert git(work, "status", "--porcelain").stdout == before


def prepare_finish(python_exe, tmp_path):
    repo, result = start_adhoc(python_exe, tmp_path)
    work = Path(payload(result)["worktree"])
    root = work / "changes/unreleased/update-readme"
    path = root / "objectives.md"
    path.write_text(path.read_text().replace("[ ]", "[x]"))
    write_change(root)
    commit(work)
    return repo, work


def test_adhoc_finish_keeps_source_tip_when_develop_has_no_worktree(python_exe, tmp_path):
    repo, work = prepare_finish(python_exe, tmp_path)
    source = git(work, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "master")
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert git(repo, "branch", "--show-current").stdout.strip() == "master"
    assert git(work, "rev-parse", "HEAD").stdout.strip() == source
    status = payload(mdf(python_exe, "adhoc-status", "--repo", str(work), "--slug", "update-readme"))["result"]
    assert status["completed"] and status["merge_commit"]


def test_adhoc_finish_resumes_cleanup_without_repeating_merge(python_exe, tmp_path):
    repo, work = prepare_finish(python_exe, tmp_path)
    git(repo, "merge", "--no-ff", "adhoc/update-readme", "-m", "test: 模拟合并后清理中断")
    merged = git(repo, "rev-parse", "develop").stdout.strip()
    status = payload(mdf(python_exe, "adhoc-status", "--repo", str(work)))["result"]
    assert not status["completed"] and status["merge_commit"] == merged
    assert status["next_step"] == "close-out"
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    assert git(repo, "rev-parse", "develop").stdout.strip() == merged
    assert not git(repo, "for-each-ref", "refs/heads/adhoc/").stdout
    assert payload(mdf(python_exe, "adhoc-status", "--repo", str(work),
                       "--slug", "update-readme"))["result"]["completed"]


def test_detached_adhoc_needs_known_slug_and_actual_no_ff_merge(python_exe, tmp_path):
    _, work = prepare_finish(python_exe, tmp_path)
    git(work, "checkout", "--detach")
    git(work, "branch", "-D", "adhoc/update-readme")
    result = mdf(python_exe, "adhoc-status", "--repo", str(work))
    assert result.returncode != 0 and "invalid_slug" in result.stderr
    result = mdf(python_exe, "adhoc-status", "--repo", str(work), "--slug", "update-readme")
    assert result.returncode != 0 and "adhoc_not_finished" in result.stderr


def test_finished_adhoc_cannot_claim_changed_local_material_as_delivered(python_exe, tmp_path):
    _, work = prepare_finish(python_exe, tmp_path)
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(work)))
    path = work / "changes/unreleased/update-readme/delivery.json"
    data = json.loads(path.read_text())
    data["work"] = "另一个未交付的需求"
    path.write_text(json.dumps(data))
    result = mdf(python_exe, "adhoc-status", "--repo", str(work), "--slug", "update-readme")
    assert result.returncode != 0 and "dirty_worktree" in result.stderr
    assert json.loads(path.read_text())["work"] == "另一个未交付的需求"


def test_adhoc_status_runs_through_cli_entry(python_exe, tmp_path):
    repo, result = start_adhoc(python_exe, tmp_path)
    work = Path(payload(result)["worktree"])
    before = git(work, "status", "--porcelain").stdout
    result = run([python_exe, str(skill_dir("mdf") / "scripts/mdf.py"),
                  "adhoc-status", "--repo", str(work)], cwd=work)
    data = payload(result)["result"]
    assert data["next_step"] == "工作" and data["primary_worktree"] == str(repo)
    assert git(work, "status", "--porcelain").stdout == before
