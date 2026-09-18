"""Feature gate、内容失效、并行集成与实际 Gitflow 交付。"""
from mdf_test_support import *  # noqa: F403
from test_mdf_gitflow_delivery import start_repo


def commit(repo, message="test: 提交当前阶段"):
    git(repo, "add", "--all")
    git(repo, "commit", "-m", message)


def git_primary(repo):
    raw = git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    path = Path(raw)
    if not path.is_absolute():
        path = (repo / path).resolve()
    else:
        path = path.resolve()
    return path.parent


def role_paths(python_exe, owner):
    trees = payload(mdf(python_exe, "delivery", "status", "--repo", str(owner))
                    )["result"]["worktrees"]
    return Path(trees["qa"][0]["path"]), Path(trees["dev"][0]["path"])


def sync_roles(python_exe, owner):
    qa, dev = role_paths(python_exe, owner)
    branch = git(owner, "branch", "--show-current").stdout.strip()
    message = f"chore(delivery): 合入 {branch}"
    for path in (qa, dev):
        git(path, "merge", "--no-ff", "--no-edit", "-m", message, branch)
    return qa, dev


def setup_delivery(python_exe, tmp_path):
    repo, remote = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n实现健康状态接口。\n")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                       "--proposal", "prp-001", "--objectives-file", str(obj)))
    work = Path(data["worktree"])
    primary = git_primary(work)
    assert work == (
        primary.parent / f"{primary.name}-worktrees" / "feature" / "service-health"
    )
    qa = Path(data["roles"]["qa"][0]["worktree"])
    assert qa == (
        primary.parent / f"{primary.name}-worktrees" / "qa" / "feature"
        / "service-health"
    )
    root = work / "changes/unreleased/service-health"
    assert json.loads((root / "delivery.json").read_text())["start_commit"] == data["start_commit"]
    objectives = root / "objectives.md"
    objectives.write_text(objectives.read_text() + "\n[design.md](./design.md)\n")
    (root / "design.md").write_text(
        "# 设计\n\n[实现](../../../src/service.py)\n\n"
        "[objectives.md](./objectives.md)\n"
        "[see design.md](./design.md)\n"
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"protected_paths": ["tests/", "pytest.ini"]}))
    payload(mdf(python_exe, "delivery", "record", "--repo", str(work), "--stage", "design",
                "--policy-file", str(policy), "--summary", "用户确认接口及验收；测试配置已识别"))
    commit(work)
    return work, root, remote


def write_change_in_place(repo, root):
    """在交付目录原地补齐 canonical CHANGE.md，并把 PRP 恢复为 ready。"""
    write_unreleased_change(repo, "temporary")
    text = (repo / "changes/unreleased/temporary/CHANGE.md").read_text()
    (root / "CHANGE.md").write_text(text.replace("feature/temporary", "feature/service-health")
                                    .replace("fixed: [bug-CD34]", "fixed: []"))
    shutil.rmtree(repo / "changes/unreleased/temporary")
    replace(repo / "docs/proposals" / PRP_NAME, "status: implemented", "status: ready")


def record(python_exe, repo, stage, *extra):
    return mdf(python_exe, "delivery", "record", "--repo", str(repo), "--stage", stage,
               "--summary", "按目标逐项核对，相关结果已复核", *extra)


def test_stages_parallel_green_and_expiry(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    result = record(python_exe, repo, "converge")
    assert result.returncode != 0
    (qa / "tests").mkdir(exist_ok=True)
    (qa / "tests/test_health.py").write_text("def test_health():\n    assert 1 == 1\n")
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(repo)))
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    payload(record(python_exe, repo, "converge"))
    payload(record(python_exe, repo, "code-review"))
    payload(record(python_exe, repo, "fact-update"))
    payload(mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish"))
    fact = repo / "docs/user-guide/README.md"
    fact.write_text(fact.read_text() + "\n补充事实说明。\n")
    result = mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish")
    assert "stale_gate" in result.stderr
    payload(record(python_exe, repo, "fact-update"))
    payload(mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish"))
    implementation = repo / "src/service.py"
    implementation.write_text(implementation.read_text() + "\n# changed\n")
    result = record(python_exe, repo, "code-review")
    assert "stale_verification" in result.stderr


def test_tests_only_change_does_not_expire_fact_update(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    (qa / "tests").mkdir(exist_ok=True)
    (qa / "tests/test_health.py").write_text("def test_health():\n    assert 1 == 1\n")
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(repo)))
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    for stage in ("converge", "code-review", "fact-update"):
        payload(record(python_exe, repo, stage))
    commit(repo)
    fact_update = (root / "gates/fact-update.json").read_text()
    # 纯测试改动：全绿与 code-review 过期，重验重审后 fact-update 仍有效。
    test_file = repo / "tests/test_health.py"
    test_file.write_text(test_file.read_text() + "\n\ndef test_more():\n    assert True\n")
    result = mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish")
    assert "stale_verification" in result.stderr
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    payload(record(python_exe, repo, "code-review"))
    payload(mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish"))
    assert (root / "gates/fact-update.json").read_text() == fact_update
    # 实现改动：重验重审后 fact-update 仍过期。
    implementation = repo / "src/service.py"
    implementation.write_text(implementation.read_text() + "\n# changed\n")
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    payload(record(python_exe, repo, "code-review"))
    result = mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish")
    assert "stale_gate" in result.stderr


def test_converge_needs_test_approval_but_review_can_repair_tests(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(repo)))
    (repo / "pytest.ini").write_text("[pytest]\n")
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    assert "test_approval_required" in record(python_exe, repo, "converge").stderr
    payload(record(python_exe, repo, "converge", "--test-approval", "用户明确确认增加配置"))
    (repo / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    payload(record(python_exe, repo, "code-review"))
    assert (root / "gates/code-review.json").is_file()


def test_partial_verification_does_not_satisfy_full_gate(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(repo)))
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo), "--item", "check"))
    assert record(python_exe, repo, "converge").returncode != 0
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace('command: "true"', 'command: "false"'))
    failed = mdf(python_exe, "delivery", "verify", "--repo", str(repo))
    assert "verify_command_failed" in failed.stderr
    assert json.loads((root / "gates/verification.json").read_text())["all_passed"] is False


def test_uncommitted_design_and_changed_design_block(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    (dev / "changes/unreleased/service-health/design.md").write_text("# 未确认的新设计\n")
    assert "stale_gate" in record(python_exe, dev, "implement").stderr


@pytest.mark.parametrize("conflict", [False, True])
def test_move_and_finish_preserve_baseline_and_release_state(python_exe, tmp_path, conflict):
    repo, root, remote = setup_delivery(python_exe, tmp_path)
    original = json.loads((root / "delivery.json").read_text())
    qa, dev = sync_roles(python_exe, repo)
    (dev / "src/service.py").write_text("value = 1\n")
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(repo)))
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    for stage in ("converge", "code-review", "fact-update"):
        payload(record(python_exe, repo, stage))
    commit(repo)
    recorded = json.loads((root / "gates/design.json").read_text())["fingerprints"]["design"]
    write_change_in_place(repo, root)
    commit(repo)
    checked = payload(mdf(python_exe, "delivery", "check", "--repo", str(repo),
                           "--stage", "finish"))["result"]
    assert checked["design"] == recorded
    if conflict:
        git(repo, "checkout", "develop")
        (repo / "src/service.py").write_text("value = 2\n")
        commit(repo)
        git(repo, "checkout", "feature/service-health")
        result = mdf(python_exe, "finish-gitflow", "--repo", str(repo))
        assert "merge_conflict" in result.stderr
        assert "status: ready" in (repo / "docs/proposals" / PRP_NAME).read_text()
        assert "implemented" not in git(
            repo, "show",
            f"feature/service-health:docs/proposals/{PRP_NAME}",
        ).stdout
        assert not git(repo, "status", "--porcelain").stdout
        return
    primary = git_primary(repo)
    payload(mdf(python_exe, "finish-gitflow", "--repo", str(repo)))
    assert not repo.exists()
    assert "implemented" in git(primary, "show", f"develop:docs/proposals/{PRP_NAME}").stdout
    dest_json = git(primary, "show",
                    "develop:changes/unreleased/service-health/delivery.json").stdout
    assert json.loads(dest_json) == original
    assert not git(primary, "for-each-ref",
                   "refs/heads/feature/service-health").stdout


def test_parallel_worktrees_independent_gates_and_cleanup(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    primary = git_primary(repo)
    container = primary.parent / f"{primary.name}-worktrees"
    assert qa == container / "qa" / "feature" / "service-health"
    assert dev == container / "dev" / "feature" / "service-health"
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


def test_status_lists_role_worktrees(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    first = payload(mdf(python_exe, "delivery", "status", "--repo", str(repo))
                    )["result"]["worktrees"]
    assert first["qa"][0]["branch"] == "qa/feature/service-health"
    assert first["dev"][0]["branch"] == "dev/feature/service-health"
    qa, _dev = sync_roles(python_exe, repo)
    again = payload(mdf(python_exe, "delivery", "status", "--repo", str(qa))
                    )["result"]["worktrees"]
    assert Path(again["qa"][0]["path"]) == qa
    assert Path(again["owner"]["path"]) == repo


def test_write_tests_rejected_on_owner(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    result = record(python_exe, repo, "write-tests")
    assert "stage_branch" in result.stderr


def test_finish_rejects_pending_role_branches(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    git(repo, "merge", "--no-ff", "--no-edit", "-m",
        "chore(delivery): 合入 qa/feature/service-health",
        "qa/feature/service-health")
    git(repo, "merge", "--no-ff", "--no-edit", "-m",
        "chore(delivery): 合入 dev/feature/service-health",
        "dev/feature/service-health")
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    for stage in ("converge", "code-review", "fact-update"):
        payload(record(python_exe, repo, stage))
    commit(repo)
    write_change_in_place(repo, root)
    commit(repo)
    result = mdf(python_exe, "finish-gitflow", "--repo", str(repo))
    assert "roles_pending" in result.stderr


def test_executable_mode_and_design_fragment_changes_invalidate_evidence(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    before = json.loads((root / "gates/design.json").read_text())["fingerprints"]
    qa, dev = sync_roles(python_exe, repo)
    (dev / "src/service.py").chmod(0o755)
    data = payload(mdf(python_exe, "delivery", "check", "--repo", str(dev),
                       "--stage", "implement"))["result"]
    assert data["code"] != before["code"]
    design = dev / "changes/unreleased/service-health/design.md"
    design.write_text(design.read_text().replace("service.py)", "service.py#new)"))
    commit(dev)
    assert "stale_gate" in record(python_exe, dev, "implement").stderr


def test_non_fact_docs_do_not_expire_review_or_green(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(repo)))
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    for stage in ("converge", "code-review", "fact-update"):
        payload(record(python_exe, repo, stage))
    commit(repo)
    before = payload(mdf(python_exe, "delivery", "check", "--repo", str(repo),
                          "--stage", "finish"))["result"]
    adr = repo / "docs/context/adr/example.md"
    adr.parent.mkdir(parents=True, exist_ok=True)
    adr.write_text("# 记录一次架构决策。\n")
    (repo / "AGENTS.md").write_text((repo / "AGENTS.md").read_text() + "\n补充说明。\n")
    (root / "CHANGE.md").write_text("# 草稿\n")
    after = payload(mdf(python_exe, "delivery", "check", "--repo", str(repo),
                         "--stage", "finish"))["result"]
    assert after["code"] == before["code"]
    assert after["facts"] == before["facts"]


def test_design_fingerprint_stable_across_sibling_href_spelling(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    recorded = json.loads((root / "gates/design.json").read_text())["fingerprints"]["design"]
    for name in ("design.md", "objectives.md"):
        path = root / name
        path.write_text(path.read_text().replace("(./", "("))
    commit(repo)
    current = payload(mdf(python_exe, "delivery", "check", "--repo", str(repo),
                           "--stage", "design"))["result"]
    assert current["design"] == recorded


def test_canonical_local_link_missing_is_not_delivery_internal(tmp_path: Path):
    load_core_module()
    from mdf_core.validate_links import canonical_local_link

    repo = copy_fixture(tmp_path)
    root = repo / "changes/unreleased/service-health"
    root.mkdir(parents=True)
    source = root / "objectives.md"
    source.write_text("# 目标\n")
    (root / "design.md").write_text("# 设计\n")
    ghost = canonical_local_link(
        repo, source, f"docs/proposals/{PRP_NAME}", root
    )
    assert ghost == (
        f"changes/unreleased/service-health/docs/proposals/{PRP_NAME}"
    )
    assert not ghost.startswith("@delivery/")
    real = canonical_local_link(
        repo, source, f"../../../docs/proposals/{PRP_NAME}", root
    )
    assert real == f"docs/proposals/{PRP_NAME}"
    sibling = canonical_local_link(repo, source, "design.md", root)
    assert sibling == "@delivery/design.md"


def test_record_design_rejects_repo_root_style_links(
    python_exe: str, tmp_path: Path
):
    repo, _ = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n实现健康状态接口。\n")
    data = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj),
    ))
    work = Path(data["worktree"])
    root = work / "changes/unreleased/service-health"
    (root / "design.md").write_text(
        "# 设计\n\n[能力](docs/user-guide/README.md)\n"
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"protected_paths": ["tests/", "pytest.ini"]}))
    result = mdf(
        python_exe, "delivery", "record", "--repo", str(work),
        "--stage", "design", "--policy-file", str(policy),
        "--summary", "用户确认接口及验收；测试配置已识别",
    )
    assert result.returncode != 0
    assert "broken_link" in result.stderr

