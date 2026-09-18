"""roster 冻结、角色分支命名与 start/integrate 行为。"""
from mdf_test_support import *  # noqa: F403
from test_mdf_gitflow_delivery import local_repo
from test_mdf_delivery import record, commit


def test_freeze_roster_defaults_and_coercion():
    load_core_module()
    from mdf_core.errors import MDFError
    from mdf_core.roster import freeze_roster, role_branch, require_roster
    assert freeze_roster("feature") == {"qa": 1, "dev": 1, "reviewers": 3}
    assert freeze_roster("bugfix") == {"qa": 0, "dev": 0, "reviewers": 3}
    assert freeze_roster("feature", 0, 0, 2) == {
        "qa": 0, "dev": 0, "reviewers": 2,
    }
    assert freeze_roster("feature", 0, 2, None) == {
        "qa": 1, "dev": 2, "reviewers": 3,
    }
    assert freeze_roster("bugfix", 2, 0, 4) == {
        "qa": 2, "dev": 1, "reviewers": 4,
    }
    assert role_branch("qa", "feature/foo", 1) == "qa/feature/foo"
    assert role_branch("qa", "feature/foo", 2) == "qa/2/feature/foo"
    with pytest.raises(MDFError, match="至少为 1"):
        freeze_roster("feature", 1, 1, 0)
    with pytest.raises(MDFError, match="同时为 0"):
        require_roster({"qa": 0, "dev": 1, "reviewers": 3})


def test_start_feature_zero_roster_has_no_role_trees(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n交付健康接口。\n")
    result = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "feature",
        "--proposal", "prp-001", "--objectives-file", str(obj),
        "--qa", "0", "--dev", "0",
    ))
    assert result["roster"] == {"qa": 0, "dev": 0, "reviewers": 3}
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
    assert result["roster"] == {"qa": 1, "dev": 2, "reviewers": 3}
    assert result["roles"]["qa"][0]["branch"] == "qa/feature/service-health"
    assert result["roles"]["dev"][1]["branch"] == "dev/2/feature/service-health"
    assert Path(result["roles"]["dev"][1]["worktree"]).is_dir()


def test_start_bugfix_can_set_reviewers_and_roles(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    plain = payload(mdf(
        python_exe, "start", "--repo", str(repo), "--kind", "bugfix",
        "--bug", "bug-CD34", "--reviewers", "2",
    ))
    assert plain["roster"] == {"qa": 0, "dev": 0, "reviewers": 2}
    assert plain["roles"] == {"qa": [], "dev": []}
    key = "branch.bugfix/bug-CD34.mdf-roster"
    raw = git(Path(plain["worktree"]), "config", "--local", "--get", key)
    assert json.loads(raw.stdout.strip()) == plain["roster"]


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
    policy.write_text(json.dumps({"protected_paths": ["tests/", "pytest.ini"]}))
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
    policy.write_text(json.dumps({"protected_paths": ["tests/", "pytest.ini"]}))
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
