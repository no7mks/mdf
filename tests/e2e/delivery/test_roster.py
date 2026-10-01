"""roster 冻结、角色分支命名与 start/integrate 行为。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def frozen(qa, dev, reviewers, **extra):
    body = {
        "qa": qa,
        "dev": dev,
        "reviewers": reviewers,
        "qa_strategy": "best-of-n",
        "dev_strategy": "best-of-n",
        "review_strategy": "replicate",
    }
    body.update(extra)
    return body


def test_start_feature_zero_roster_has_no_role_trees(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n交付健康接口。\n")
    result = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj),
        "--qa", "0", "--dev", "0",
    ))
    assert result["roster"] == frozen(0, 0, 2)
    assert result["roles"] == {"qa": [], "dev": []}
    work = Path(result["worktree"])
    identity = json.loads(
        (work / "changes/unreleased/service-health/delivery.json").read_text()
    )
    assert identity["roster"] == result["roster"]
    assert not (work.parent / "qa").exists()


def test_start_feature_two_devs_creates_indexed_branches(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n交付健康接口。\n")
    result = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj),
        "--qa", "0", "--dev", "2",
    ))
    assert result["roster"] == frozen(1, 2, 2)
    assert result["roles"]["qa"][0]["branch"] == "qa/feature/service-health"
    assert result["roles"]["dev"][1]["branch"] == "dev/2/feature/service-health"
    assert Path(result["roles"]["dev"][1]["worktree"]).is_dir()


def test_start_bugfix_can_set_reviewers_and_roles(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    plain = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--bug", "bug-CD34", "--reviewers", "2",
        "--objectives-file", str(write_work_objectives(tmp_path)),
    ))
    assert plain["roster"] == frozen(0, 0, 2)
    assert plain["roles"] == {"qa": [], "dev": []}
    key = "branch.bugfix/bug-CD34.mdf-roster"
    raw = git(Path(plain["worktree"]), "config", "--local", "--get", key)
    assert json.loads(raw.stdout.strip()) == plain["roster"]


def test_start_named_roster_expands_and_overlays(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n交付健康接口。\n")
    coop = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj),
        "--roster", "coop-pair",
    ))
    assert coop["roster"] == frozen(
        2, 2, 3, qa_strategy="partition", dev_strategy="partition",
    )
    assert len(coop["roles"]["qa"]) == 2
    assert len(coop["roles"]["dev"]) == 2
    assert "named" not in coop["roster"]
    (tmp_path / "overlay").mkdir()
    repo2 = local_repo(tmp_path / "overlay")
    obj2 = tmp_path / "overlay-objectives.md"
    obj2.write_text("# 目标\n\n交付健康接口。\n")
    mixed = payload(mdf(
        python_exe, "start", "--repo", str(repo2), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj2),
        "--roster", "competing-pair", "--qa", "3",
    ))
    assert mixed["roster"] == frozen(3, 2, 3)
    assert len(mixed["roles"]["qa"]) == 3


def test_start_freezes_strategy_and_models(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n交付健康接口。\n")
    result = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj),
        "--qa-strategy", "partition", "--dev-strategy", "partition",
        "--review-strategy", "partition",
        "--write-tests-model", "composer",
        "--code-review-model", "opus",
    ))
    expected = frozen(
        1, 1, 2, qa_strategy="partition", dev_strategy="partition",
        review_strategy="partition",
        models={"write-tests": "composer", "code-review": "opus"},
    )
    assert result["roster"] == expected
    work = Path(result["worktree"])
    identity = json.loads(
        (work / "changes/unreleased/service-health/delivery.json").read_text()
    )
    assert identity["roster"] == expected


def test_write_tests_on_owner_when_roster_zero(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n交付健康接口。\n")
    started = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj),
        "--qa", "0", "--dev", "0",
    ))
    work = Path(started["worktree"])
    root = work / "changes/unreleased/service-health"
    (root / "design.md").write_text(
        "# 设计\n\n[objectives.md](./objectives.md)\n"
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"protected_paths": ["tests/", "pytest.ini"], "suites": ["billing"]}))
    payload(mdf(
        python_exe, "delivery", "record", "--repo", str(work), "--stage",
        "design", "--policy-file", str(policy), "--summary", "确认设计",
    ))
    commit(work)
    payload(record(python_exe, work, "write-tests"))
    commit(work)
    payload(record(python_exe, work, "implement"))
    commit(work)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(work)))
    assert (root / "gates/integration.json").is_file()


def test_integrate_two_devs_merges_winner_and_deletes_loser(
    python_exe, tmp_path,
):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n交付健康接口。\n")
    started = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj),
        "--qa", "1", "--dev", "2",
    ))
    owner = Path(started["worktree"])
    root = owner / "changes/unreleased/service-health"
    (root / "design.md").write_text(
        "# 设计\n\n[objectives.md](./objectives.md)\n"
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"protected_paths": ["tests/", "pytest.ini"], "suites": ["billing"]}))
    payload(mdf(
        python_exe, "delivery", "record", "--repo", str(owner), "--stage",
        "design", "--policy-file", str(policy), "--summary", "确认设计",
    ))
    commit(owner)
    qa = Path(started["roles"]["qa"][0]["worktree"])
    winner = Path(started["roles"]["dev"][1]["worktree"])
    loser = Path(started["roles"]["dev"][0]["worktree"])
    message = "chore(delivery): 合入 feature/service-health"
    for path in (qa, winner, loser):
        git(path, "merge", "--no-ff", "--no-edit", "-m", message,
            "feature/service-health")
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    (winner / "src/implemented.py").write_text("value = 2\n")
    payload(record(python_exe, winner, "implement"))
    commit(winner)
    missing = mdf(python_exe, "delivery", "integrate", "--repo", str(owner))
    assert "missing_winner" in missing.stderr
    payload(mdf(
        python_exe, "delivery", "integrate", "--repo", str(owner),
        "--dev-branch", "dev/2/feature/service-health",
    ))
    assert not qa.exists() and not winner.exists() and not loser.exists()
    assert (owner / "src/implemented.py").read_text() == "value = 2\n"
    assert not git(
        owner, "for-each-ref", "refs/heads/dev/feature/service-health",
    ).stdout
    assert not git(
        owner, "for-each-ref", "refs/heads/dev/2/feature/service-health",
    ).stdout


def _design_feature(python_exe, tmp_path, *start_args):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n交付健康接口。\n")
    started = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj), *start_args,
    ))
    owner = Path(started["worktree"])
    root = owner / "changes/unreleased/service-health"
    (root / "design.md").write_text(
        "# 设计\n\n[objectives.md](./objectives.md)\n"
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"protected_paths": ["tests/", "pytest.ini"], "suites": ["billing"]}))
    return started, owner, root, policy


def test_delivery_roster_locks_qa_dev_after_design(python_exe, tmp_path):
    started, owner, root, policy = _design_feature(python_exe, tmp_path)
    payload(mdf(
        python_exe, "delivery", "roster", "--repo", str(owner),
        "--qa-strategy", "partition", "--code-review-model", "review high",
    ))
    identity = json.loads((root / "delivery.json").read_text())
    assert identity["roster"]["qa_strategy"] == "partition"
    assert identity["roster"]["models"] == {"code-review": "review high"}
    payload(mdf(
        python_exe, "delivery", "record", "--repo", str(owner), "--stage",
        "design", "--policy-file", str(policy), "--summary", "确认设计",
    ))
    commit(owner)
    locked = mdf(
        python_exe, "delivery", "roster", "--repo", str(owner),
        "--qa-strategy", "best-of-n",
    )
    assert "roster_locked" in locked.stderr
    payload(mdf(
        python_exe, "delivery", "roster", "--repo", str(owner),
        "--review-strategy", "partition",
    ))
    commit(owner)
    qa = Path(started["roles"]["qa"][0]["worktree"])
    git(qa, "merge", "--no-ff", "--no-edit", "-m",
        "chore(delivery): 合入 feature/service-health",
        "feature/service-health")
    payload(record(python_exe, qa, "write-tests"))


def test_delivery_roster_merges_models_by_intent(python_exe, tmp_path):
    _started, owner, root, _policy = _design_feature(
        python_exe, tmp_path, "--write-tests-model", "composer",
    )
    payload(mdf(
        python_exe, "delivery", "roster", "--repo", str(owner),
        "--code-review-model", "opus",
    ))
    identity = json.loads((root / "delivery.json").read_text())
    assert identity["roster"]["models"] == {
        "write-tests": "composer", "code-review": "opus",
    }


def test_integrate_partition_merges_all_dev_branches(python_exe, tmp_path):
    started, owner, root, policy = _design_feature(
        python_exe, tmp_path, "--qa", "1", "--dev", "2",
        "--dev-strategy", "partition",
    )
    payload(mdf(
        python_exe, "delivery", "record", "--repo", str(owner), "--stage",
        "design", "--policy-file", str(policy), "--summary", "确认设计",
    ))
    commit(owner)
    qa = Path(started["roles"]["qa"][0]["worktree"])
    first = Path(started["roles"]["dev"][0]["worktree"])
    second = Path(started["roles"]["dev"][1]["worktree"])
    message = "chore(delivery): 合入 feature/service-health"
    for path in (qa, first, second):
        git(path, "merge", "--no-ff", "--no-edit", "-m", message,
            "feature/service-health")
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    (first / "src/one.py").write_text("one = 1\n")
    payload(record(python_exe, first, "implement"))
    commit(first)
    (second / "src/two.py").write_text("two = 2\n")
    payload(record(python_exe, second, "implement"))
    commit(second)
    unexpected = mdf(
        python_exe, "delivery", "integrate", "--repo", str(owner),
        "--dev-branch", "dev/2/feature/service-health",
    )
    assert "unexpected_winner" in unexpected.stderr
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(owner)))
    assert (owner / "src/one.py").read_text() == "one = 1\n"
    assert (owner / "src/two.py").read_text() == "two = 2\n"
    assert not first.exists() and not second.exists() and not qa.exists()


def test_converge_partition_qa_uses_merged_tests_baseline(python_exe, tmp_path):
    started, owner, root, policy = _design_feature(
        python_exe, tmp_path, "--roster", "coop-pair",
    )
    payload(mdf(
        python_exe, "delivery", "record", "--repo", str(owner), "--stage",
        "design", "--policy-file", str(policy), "--summary", "确认设计",
    ))
    commit(owner)
    message = "chore(delivery): 合入 feature/service-health"
    lanes = [
        (Path(item["worktree"]), stage, path)
        for role, stage, paths in (
            ("qa", "write-tests", ("tests/test_one.py", "tests/test_two.py")),
            ("dev", "implement", ("src/one.py", "src/two.py")),
        )
        for item, path in zip(started["roles"][role], paths)
    ]
    for work, stage, path in lanes:
        git(work, "merge", "--no-ff", "--no-edit", "-m", message,
            "feature/service-health")
        (work / path).parent.mkdir(exist_ok=True)
        (work / path).write_text("def test_value():\n    assert True\n")
        payload(record(python_exe, work, stage))
        commit(work)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(owner)))
    assert (owner / "tests/test_one.py").is_file()
    assert (owner / "tests/test_two.py").is_file()
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(owner)))
    payload(record(python_exe, owner, "converge"))
    edited = owner / "tests/test_two.py"
    edited.write_text(edited.read_text() + "\n\ndef test_more():\n    assert True\n")
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(owner)))
    assert "test_approval_required" in record(
        python_exe, owner, "converge",
    ).stderr


def test_bugfix_roster_update_without_delivery_json(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    started = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--bug", "bug-CD34",
        "--objectives-file", str(write_work_objectives(tmp_path)),
    ))
    work = Path(started["worktree"])
    updated = payload(mdf(
        python_exe, "delivery", "roster", "--repo", str(work),
        "--review-strategy", "partition", "--code-review-model", "review high",
    ))["result"]
    assert updated["review_strategy"] == "partition"
    assert updated["models"] == {"code-review": "review high"}
    key = "branch.bugfix/bug-CD34.mdf-roster"
    raw = git(work, "config", "--local", "--get", key)
    assert json.loads(raw.stdout.strip()) == updated
