"""Feature 阶段快照、并行集成与实际 Gitflow 交付（record 非进度 gate）。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def write_change_in_place(repo, root):
    """在交付目录原地补齐 canonical CHANGE.md，并把 PRP 恢复为 ready。"""
    write_unreleased_change(repo, "temporary")
    text = (repo / "changes/unreleased/temporary/CHANGE.md").read_text()
    (root / "CHANGE.md").write_text(text.replace("feature/temporary", "feature/service-health")
                                    .replace("fixed: [bug-CD34]", "fixed: []"))
    shutil.rmtree(repo / "changes/unreleased/temporary")
    replace(repo / "docs/proposals" / PRP_NAME, "status: implemented", "status: ready")


def test_stages_parallel_green_and_finish_without_code_review_gate(python_exe, tmp_path):
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
    payload(mdf(python_exe, "delivery", "roster-join", "--repo", str(repo)))
    # finish 只核材料存在；不以 converge gate 为进度关口（配置快照仍可 record）
    payload(mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish"))
    payload(record(python_exe, repo, "converge"))
    payload(mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish"))
    rejected = mdf(
        python_exe, "delivery", "record", "--repo", str(repo),
        "--stage", "code-review", "--summary", "不应接受",
    )
    assert rejected.returncode != 0
    # 实现改动不使 finish CLI 因审查 fingerprint 失败
    implementation = repo / "src/service.py"
    implementation.write_text(implementation.read_text() + "\n# changed\n")
    payload(mdf(python_exe, "delivery", "check", "--repo", str(repo), "--stage", "finish"))


def test_converge_needs_test_approval_but_review_can_repair_tests(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    payload(mdf(python_exe, "delivery", "roster-join", "--repo", str(repo)))
    (repo / "pytest.ini").write_text("[pytest]\n")
    assert "test_approval_required" in record(python_exe, repo, "converge").stderr
    payload(record(python_exe, repo, "converge", "--test-approval", "用户明确确认增加配置"))
    (repo / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    assert not (root / "gates/code-review.json").exists()


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
    payload(mdf(python_exe, "delivery", "roster-join", "--repo", str(repo)))
    payload(record(python_exe, repo, "converge"))
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
    assert repo.is_dir()
    assert not git(repo, "branch", "--show-current").stdout.strip()
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
    payload(mdf(python_exe, "delivery", "roster-join", "--repo", str(repo)))
    assert not qa.exists() and not dev.exists()
    assert (repo / "src/implemented.py").exists()
    assert (repo / "tests/test_case.py").exists()
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
    payload(record(python_exe, repo, "converge"))
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


def test_non_fact_docs_do_not_expire_finish_check(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    payload(mdf(python_exe, "delivery", "roster-join", "--repo", str(repo)))
    payload(record(python_exe, repo, "converge"))
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


def test_start_requires_needs_design(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n没有 needs_design 字段。\n")
    result = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-0001", "--objectives-file", str(obj),
    )
    assert result.returncode != 0
    assert "missing_needs_design" in result.stderr


def test_start_release_requires_has_dev(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 发布目标\n\n- needs_design: no\n\n缺少 has_dev。\n")
    result = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "release",
        "--version", "1.3.0", "--objectives-file", str(obj),
    )
    assert result.returncode != 0
    assert "missing_has_dev" in result.stderr


def test_roster_requires_needs_design_yes(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n- needs_design: no\n\n实现。\n")
    result = mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-0001", "--objectives-file", str(obj),
    )
    assert result.returncode != 0
    assert "invalid_needs_design" in result.stderr


def test_record_design_rejects_repo_root_style_links(
    python_exe: str, tmp_path: Path
):
    repo, _ = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n- needs_design: yes\n\n实现健康状态接口。\n")
    data = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-0001", "--objectives-file", str(obj),
    ))
    work = Path(data["worktree"])
    root = work / "changes/unreleased/service-health"
    (root / "design.md").write_text(
        "# 设计\n\n[能力](docs/user-guide/README.md)\n"
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({
        "protected_paths": ["tests/", "pytest.ini"], "suites": ["billing"],
    }))
    result = mdf(
        python_exe, "delivery", "record", "--repo", str(work),
        "--stage", "design", "--policy-file", str(policy),
        "--summary", "用户确认接口及验收；测试配置已识别",
    )
    assert result.returncode != 0
    assert "broken_link" in result.stderr
