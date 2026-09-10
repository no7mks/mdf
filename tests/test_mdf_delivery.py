"""Feature gate、内容失效、并行集成与实际 Gitflow 交付。"""
from mdf_test_support import *  # noqa: F403
from test_mdf_gitflow_delivery import start_repo


def commit(repo, message="test: 提交当前阶段"):
    git(repo, "add", "--all")
    git(repo, "commit", "-m", message)


def setup_delivery(python_exe, tmp_path):
    repo, remote = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n实现健康状态接口。\n")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                       "--name", "health", "--proposal", "prp-AB23", "--objectives-file", str(obj)))
    root = repo / "docs/specs/health"
    assert json.loads((root / "delivery.json").read_text())["start_commit"] == data["start_commit"]
    (root / "design.md").write_text("# 设计\n\n[实现](../../../src/service.py)\n")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"protected_paths": ["tests/", "pytest.ini"]}))
    payload(mdf(python_exe, "delivery", "record", "--repo", str(repo), "--stage", "design",
                "--policy-file", str(policy), "--summary", "用户确认接口及验收；测试配置已识别"))
    commit(repo)
    return repo, root, remote


def record(python_exe, repo, stage, *extra):
    return mdf(python_exe, "delivery", "record", "--repo", str(repo), "--stage", stage,
               "--summary", "按目标逐项核对，相关结果已复核", *extra)


def test_stages_parallel_green_and_expiry(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    # Implementation need not wait for tests.
    payload(record(python_exe, repo, "implement"))
    result = record(python_exe, repo, "converge")
    assert result.returncode != 0
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests/test_health.py").write_text("def test_health():\n    assert 1 == 1\n")
    payload(record(python_exe, repo, "write-tests"))
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    payload(record(python_exe, repo, "converge"))
    payload(record(python_exe, repo, "review"))
    payload(record(python_exe, repo, "fact-update"))
    # Evidence writes do not invalidate their own results.
    payload(mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish"))
    fact = repo / "docs/product/reference/capabilities.md"
    fact.write_text(fact.read_text() + "\n补充事实说明。\n")
    result = mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish")
    assert "stale_gate" in result.stderr
    payload(record(python_exe, repo, "fact-update"))
    payload(mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish"))
    implementation = repo / "src/service.py"
    implementation.write_text(implementation.read_text() + "\n# changed\n")
    result = record(python_exe, repo, "review")
    assert "stale_verification" in result.stderr


def test_converge_needs_test_approval_but_review_can_repair_tests(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    payload(record(python_exe, repo, "write-tests"))
    payload(record(python_exe, repo, "implement"))
    (repo / "pytest.ini").write_text("[pytest]\n")
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    assert "test_approval_required" in record(python_exe, repo, "converge").stderr
    payload(record(python_exe, repo, "converge", "--test-approval", "用户明确确认增加配置"))
    (repo / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    payload(record(python_exe, repo, "review"))
    assert (root / "gates/review.json").is_file()


def test_partial_verification_does_not_satisfy_full_gate(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    payload(record(python_exe, repo, "write-tests"))
    payload(record(python_exe, repo, "implement"))
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo), "--item", "check"))
    assert record(python_exe, repo, "converge").returncode != 0
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace('command: "true"', 'command: "false"'))
    failed = mdf(python_exe, "delivery", "verify", "--repo", str(repo))
    assert "verify_command_failed" in failed.stderr
    assert json.loads((root / "gates/verification.json").read_text())["all_passed"] is False


def test_uncommitted_design_and_changed_design_block(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    (root / "design.md").write_text("# 未确认的新设计\n")
    assert "stale_gate" in record(python_exe, repo, "implement").stderr


@pytest.mark.parametrize("conflict", [False, True])
def test_move_and_finish_preserve_baseline_and_release_state(python_exe, tmp_path, conflict):
    repo, root, remote = setup_delivery(python_exe, tmp_path)
    original = json.loads((root / "delivery.json").read_text())
    (repo / "src/service.py").write_text("value = 1\n")
    for stage in ("write-tests", "implement"):
        payload(record(python_exe, repo, stage))
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    for stage in ("converge", "review", "fact-update"):
        payload(record(python_exe, repo, stage))
    commit(repo)
    payload(mdf(python_exe, "move-change", "--repo", str(repo), "--source", str(root),
                "--branch-slug", "health"))
    dest = repo / "docs/changes/unreleased/health"
    assert "../../../../src/service.py" in (dest / "design.md").read_text()
    # Existing helper creates the directory; place its CHANGE alongside the moved material.
    write_unreleased_change(repo, "temporary")
    text = (repo / "docs/changes/unreleased/temporary/CHANGE.md").read_text()
    (dest / "CHANGE.md").write_text(text.replace("feature/temporary", "feature/health")
                                    .replace("fixed: [bug-CD34]", "fixed: []"))
    shutil.rmtree(repo / "docs/changes/unreleased/temporary")
    replace(repo / "docs/proposals" / PRP_NAME, "status: implemented", "status: ready")
    commit(repo)
    payload(mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish"))
    git(repo, "push")
    if conflict:
        git(repo, "checkout", "develop")
        (repo / "src/service.py").write_text("value = 2\n")
        commit(repo)
        git(repo, "push")
        git(repo, "checkout", "feature/health")
        result = mdf(python_exe, "finish-gitflow", "--repo", str(repo))
        assert "merge_conflict" in result.stderr
        assert "status: ready" in (repo / "docs/proposals" / PRP_NAME).read_text()
        assert "implemented" not in git(repo, "show", f"origin/feature/health:docs/proposals/{PRP_NAME}").stdout
        assert not git(repo, "status", "--porcelain").stdout
        return
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo)))
    assert "implemented" in (repo / "docs/proposals" / PRP_NAME).read_text()
    assert json.loads((dest / "delivery.json").read_text()) == original
    assert git(repo, "branch", "--show-current").stdout.strip() == "develop"
    assert not git(remote, "for-each-ref", "refs/heads/feature/health").stdout


def test_parallel_worktrees_independent_gates_and_cleanup(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa = Path(payload(mdf(python_exe, "delivery", "worktree", "--repo", str(repo),
                           "--role", "qa"))["result"]["worktree"]["path"])
    dev = Path(payload(mdf(python_exe, "delivery", "worktree", "--repo", str(repo),
                            "--role", "dev"))["result"]["worktree"]["path"])
    (qa / "tests").mkdir(exist_ok=True)
    (qa / "tests/test_case.py").write_text("def test_case():\n    assert True\n")
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    (dev / "src/implemented.py").write_text("value = 1\n")
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(repo)))
    assert not qa.exists() and not dev.exists()
    assert (repo / "src/implemented.py").exists()
    assert (repo / "tests/test_case.py").exists()
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    payload(record(python_exe, repo, "converge"))


def test_worktree_requires_role(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    result = mdf(python_exe, "delivery", "worktree", "--repo", str(repo))
    assert "missing_role" in result.stderr


def test_executable_mode_and_design_fragment_changes_invalidate_evidence(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    before = json.loads((root / "gates/design.json").read_text())["fingerprints"]
    (repo / "src/service.py").chmod(0o755)
    data = payload(mdf(python_exe, "delivery", "check", "--repo", str(repo),
                       "--stage", "implement"))["result"]
    assert data["code"] != before["code"]
    design = root / "design.md"
    design.write_text(design.read_text().replace("service.py)", "service.py#new)"))
    commit(repo)
    assert "stale_gate" in record(python_exe, repo, "implement").stderr
