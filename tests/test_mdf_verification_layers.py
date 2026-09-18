"""验证集合分层：quick / full / 交付 suite 的 gate 与证据。"""
from mdf_test_support import *  # noqa: F403
from test_mdf_delivery import commit, record, setup_delivery, sync_roles
from test_mdf_gitflow_delivery import start_repo


UNLAYERED_ITEM = '    - id: check\n      kind: custom\n      command: "true"'


def layer_commands(repo, body):
    path = repo / ".mdf/manifest.yaml"
    text = path.read_text()
    assert UNLAYERED_ITEM in text
    path.write_text(text.replace(UNLAYERED_ITEM, body, 1))


def setup_layered_delivery(python_exe, tmp_path, body=None):
    repo, remote = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n实现健康状态接口。\n")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                       "--proposal", "prp-001", "--objectives-file", str(obj)))
    work = Path(data["worktree"])
    root = work / "changes/unreleased/service-health"
    objectives = root / "objectives.md"
    objectives.write_text(objectives.read_text() + "\n[design.md](./design.md)\n")
    (root / "design.md").write_text(
        "# 设计\n\n[实现](../../../src/service.py)\n\n"
        "[objectives.md](./objectives.md)\n"
        "[see design.md](./design.md)\n"
    )
    layer_commands(work, body or (
        UNLAYERED_ITEM + "\n      collections: [quick, full, billing]"
    ))
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({
        "protected_paths": ["tests/", "pytest.ini"], "suites": ["billing"],
    }))
    payload(mdf(python_exe, "delivery", "record", "--repo", str(work), "--stage", "design",
                "--policy-file", str(policy), "--summary", "用户确认接口及验收；测试配置已识别"))
    commit(work)
    return work, root, remote


def test_layered_design_requires_suites(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n实现健康状态接口。\n")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                       "--proposal", "prp-001", "--objectives-file", str(obj)))
    work = Path(data["worktree"])
    root = work / "changes/unreleased/service-health"
    (root / "objectives.md").write_text(
        (root / "objectives.md").read_text() + "\n[design.md](./design.md)\n"
    )
    (root / "design.md").write_text("# 设计\n\n[objectives.md](./objectives.md)\n")
    layer_commands(work, UNLAYERED_ITEM + "\n      collections: [quick, full]")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"protected_paths": ["tests/", "pytest.ini"]}))
    result = mdf(python_exe, "delivery", "record", "--repo", str(work), "--stage", "design",
                 "--policy-file", str(policy), "--summary", "用户确认接口及验收")
    assert "invalid_policy" in result.stderr


def test_feature_quick_only_evidence_does_not_satisfy_delivery_suite(
    python_exe, tmp_path
):
    repo, root, _ = setup_layered_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(repo)))
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    evidence = json.loads((root / "gates/verification.json").read_text())
    assert evidence["collections"] == ["quick", "billing"]
    assert evidence["all_passed"] is True
    evidence["collections"] = ["quick"]
    (root / "gates/verification.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    assert "stale_verification" in record(python_exe, repo, "converge").stderr
    evidence["collections"] = ["quick", "billing"]
    (root / "gates/verification.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    payload(record(python_exe, repo, "converge"))


def test_unlayered_verify_records_quick_and_full(python_exe, tmp_path):
    repo, root, _ = setup_delivery(python_exe, tmp_path)
    qa, dev = sync_roles(python_exe, repo)
    payload(record(python_exe, qa, "write-tests"))
    commit(qa)
    payload(record(python_exe, dev, "implement"))
    commit(dev)
    payload(mdf(python_exe, "delivery", "integrate", "--repo", str(repo)))
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    evidence = json.loads((root / "gates/verification.json").read_text())
    assert evidence["collections"] == ["quick", "full"]
    payload(record(python_exe, repo, "converge"))
