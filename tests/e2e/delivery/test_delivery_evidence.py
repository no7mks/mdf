"""worktree 身份核验、集成续办与非 feature 验证证据。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403
from support_upgrade import *  # noqa: F403


def test_worktree_check_rejects_wrong_role_and_stale_handoff(python_exe, tmp_path):
    owner, _, _ = setup_delivery(python_exe, tmp_path)
    qa, _ = sync_roles(python_exe, owner)
    design = source_head(owner)
    args = ["worktree-check", "--owner", str(owner), "--role", "qa", "--design-commit", design]
    assert "wrong_worktree" in mdf(python_exe, *args, "--repo", str(owner)).stderr
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    result = payload(mdf(python_exe, *args, "--repo", str(qa), "--handoff"))["result"]
    assert result["path"] == str(qa)
    (qa / "tests").mkdir(exist_ok=True)
    (qa / "tests/late.py").write_text("assert True\n")
    commit(qa)
    assert "stale_gate" in mdf(python_exe, *args, "--repo", str(qa), "--handoff").stderr


def test_non_feature_verification_records_run_and_rerun_after_impl_change(
    python_exe, tmp_path
):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "bugfix", "--bug", "bug-CD34",
                          "--objectives-file", str(write_work_objectives(tmp_path))))
    work = Path(created["worktree"])
    args = ["--repo", str(work)]
    suites = work / "changes/unreleased/bug-cd34/suites.json"
    suites.parent.mkdir(parents=True, exist_ok=True)
    suites.write_text(json.dumps({"suites": ["billing"]}) + "\n")
    commit(work, "test: 关联 named suite")
    payload(mdf(python_exe, "verify", "run", "--scope", "branch", *args))
    evidence = work / "changes/unreleased/bug-cd34/verify.branch.json"
    assert evidence.is_file()
    first = json.loads(evidence.read_text())
    assert first["all_passed"] is True
    assert "commit" not in first and "head" not in first
    assert not list((work / "docs/context/research").glob("code-review*"))
    (work / "src/service.py").write_text("changed = True\n")
    commit(work, "test: 改实现")
    # 报告仍声称通过；主链不以 commit 对齐作废。需要新结果时再 run。
    assert json.loads(evidence.read_text())["all_passed"] is True
    payload(mdf(python_exe, "verify", "run", "--scope", "branch", *args))
    patch_module_command(work, "quick", lambda c: "false && " + c)
    commit(work, "test: 弄坏 quick")
    assert "verify_command_failed" in mdf(python_exe, "verify", "run", "--scope", "branch", *args).stderr
    failed = json.loads(evidence.read_text())
    assert failed["all_passed"] is False


def test_roster_join_resumes_after_first_role_was_removed(python_exe, tmp_path, monkeypatch):
    owner, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, owner)
    for path, stage in ((qa, "write-tests"), (dev, "implement")):
        payload(record(python_exe, path, stage))
        commit(path)
    load_core_module()
    from mdf_core import delivery_git
    from mdf_core.delivery_state import locate
    from mdf_core.errors import MDFError
    original = delivery_git.git

    def fail_cleanup(repo, *args, **kwargs):
        if args[:2] == ("worktree", "remove") and args[2] == str(dev):
            raise MDFError("模拟第二路清理失败", code="test_interruption")
        return original(repo, *args, **kwargs)

    _, data = locate(owner)
    with monkeypatch.context() as patch:
        patch.setattr(delivery_git, "git", fail_cleanup)
        with pytest.raises(MDFError):
            delivery_git.roster_join(owner, root, data, None)
    assert not qa.exists() and dev.exists()
    merged_head = source_head(owner)
    payload(mdf(python_exe, "delivery", "roster-join", "--repo", str(owner)))
    assert source_head(owner) == merged_head
    assert not dev.exists()
    payload(mdf(python_exe, "delivery", "roster-join", "--repo", str(owner)))
    assert source_head(owner) == merged_head


def test_bugfix_requires_named_suite_and_runs_smoke(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
                          "--bug", "bug-CD34",
                          "--objectives-file", str(write_work_objectives(tmp_path))))
    work = Path(created["worktree"])
    args = ["--repo", str(work)]
    missing = mdf(python_exe, "verify", "run", "--scope", "branch", *args)
    assert "missing_delivery_suite" in missing.stderr
    suites = work / "changes/unreleased/bug-cd34/suites.json"
    suites.parent.mkdir(parents=True, exist_ok=True)
    suites.write_text(json.dumps({"suites": ["smoke"]}) + "\n")
    commit(work, "test: 误用保留 suite 名")
    reserved = mdf(python_exe, "verify", "run", "--scope", "branch", *args)
    assert "invalid_delivery_suite" in reserved.stderr
    suites.write_text(json.dumps({"suites": ["billing"]}) + "\n")
    commit(work, "test: 关联 billing")
    payload(mdf(python_exe, "verify", "run", "--scope", "branch", *args))
    path = work / "changes/unreleased/bug-cd34/verify.branch.json"
    evidence = json.loads(path.read_text())
    assert evidence["suites"] == ["quick", "smoke"]
    assert [item["id"] for item in evidence["results"]] == [
        "lint:default", "build:default", "quick:default", "smoke:default",
    ]
    assert "commit" not in evidence


def test_release_runs_release_suite(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    objectives = write_release_objectives(tmp_path)
    created = payload(
        mdf(
            python_exe,
            "start",
            "--repo",
            str(repo),
            "--kind",
            "release",
            "--version",
            "1.3.0",
            "--objectives-file",
            str(objectives),
        )
    )
    work = Path(created["worktree"])
    args = ["--repo", str(work)]
    payload(mdf(python_exe, "verify", "run", "--scope", "branch", *args))
    path = work / "changes/unreleased/1.3.0/verify.branch.json"
    evidence = json.loads(path.read_text())
    assert evidence["suites"] == ["quick", "release"]
    assert [item["id"] for item in evidence["results"]] == [
        "lint:default",
        "build:default",
        "quick:default",
        "release:default",
    ]
    assert "commit" not in evidence
