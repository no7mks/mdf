"""worktree 身份核验、集成续办与非 feature 验证证据。"""
from types import SimpleNamespace
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


def test_non_feature_verification_binds_inputs_and_records_failure(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "bugfix", "--bug", "bug-CD34"))
    work = Path(created["worktree"])
    args = ["--repo", str(work)]
    suites = work / "changes/unreleased/bug-cd34/suites.json"
    suites.parent.mkdir(parents=True, exist_ok=True)
    suites.write_text(json.dumps({"suites": ["billing"]}) + "\n")
    payload(mdf(python_exe, "project-verify", "run", *args))
    payload(mdf(python_exe, "project-verify", "check", *args))
    evidence = work / "changes/unreleased/bug-cd34/code-review.verification.json"
    assert evidence.is_file()
    assert not list((work / "docs/context/research").glob("code-review*"))
    (work / "src/service.py").write_text("changed = True\n")
    assert "stale_verification" in mdf(python_exe, "project-verify", "check", *args).stderr
    manifest = work / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace('quick: "', 'quick: "false && '))
    assert "verify_command_failed" in mdf(python_exe, "project-verify", "run", *args).stderr
    assert "stale_verification" in mdf(python_exe, "project-verify", "check", *args).stderr


def test_integration_resumes_after_first_role_was_removed(python_exe, tmp_path, monkeypatch):
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
            delivery_git.integrate(owner, root, data, None)
    assert not qa.exists() and dev.exists()
    merged_head = source_head(owner)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(owner)))
    assert source_head(owner) == merged_head
    assert not dev.exists()
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(owner)))
    assert source_head(owner) == merged_head


def test_bugfix_requires_named_suite_and_runs_smoke(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
                          "--bug", "bug-CD34"))
    work = Path(created["worktree"])
    args = ["--repo", str(work)]
    missing = mdf(python_exe, "project-verify", "run", *args)
    assert "missing_delivery_suite" in missing.stderr
    suites = work / "changes/unreleased/bug-cd34/suites.json"
    suites.parent.mkdir(parents=True, exist_ok=True)
    suites.write_text(json.dumps({"suites": ["smoke"]}) + "\n")
    reserved = mdf(python_exe, "project-verify", "run", *args)
    assert "invalid_delivery_suite" in reserved.stderr
    suites.write_text(json.dumps({"suites": ["billing"]}) + "\n")
    payload(mdf(python_exe, "project-verify", "run", *args))
    path = work / "changes/unreleased/bug-cd34/code-review.verification.json"
    evidence = json.loads(path.read_text())
    assert evidence["suites"] == ["quick", "smoke"]
    assert [item["id"] for item in evidence["results"]] == ["lint", "build", "quick", "smoke"]
    payload(mdf(python_exe, "project-verify", "check", *args))
    manifest = work / ".mdf/manifest.yaml"
    original = manifest.read_text()
    manifest.write_text(original.replace('  smoke: "', '  smoke: " ', 1))
    assert "stale_verification" in mdf(python_exe, "project-verify", "check", *args).stderr
    manifest.write_text(original)
    suites.write_text(json.dumps({"suites": ["billing", "checkout"]}) + "\n")
    assert "stale_verification" in mdf(python_exe, "project-verify", "check", *args).stderr
    suites.write_text(json.dumps({"suites": ["billing"]}) + "\n")
    evidence["suites"] = ["quick"]
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    assert "stale_verification" in mdf(python_exe, "project-verify", "check", *args).stderr


def test_release_runs_release_suite_and_rejects_smoke_evidence(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    created = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "release",
                          "--version", "1.3.0", "--objectives-file",
                          str(write_release_objectives(tmp_path))))
    work = Path(created["worktree"])
    args = ["--repo", str(work)]
    payload(mdf(python_exe, "project-verify", "run", *args))
    path = work / "changes/unreleased/1.3.0/code-review.verification.json"
    evidence = json.loads(path.read_text())
    assert evidence["suites"] == ["quick", "release"]
    assert [item["id"] for item in evidence["results"]] == ["lint", "build", "quick", "release"]
    evidence["suites"] = ["quick", "smoke"]
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    assert "stale_verification" in mdf(python_exe, "project-verify", "check", *args).stderr
