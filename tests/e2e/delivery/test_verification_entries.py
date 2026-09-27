"""验证入口：lint、build 与 quick/smoke/release 的 gate、预算与证据。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


@pytest.mark.parametrize("policy", [
    {"protected_paths": ["tests/"]},
    {"protected_paths": ["tests/"], "suites": []},
    {"protected_paths": ["tests/"], "suites": ["smoke"]},
    {"protected_paths": ["tests/"], "suites": ["lint"]},
    {"protected_paths": ["tests/"], "suites": ["release"]},
    {"protected_paths": ["tests/"], "suites": ["full"]},
])
def test_design_requires_named_suites(python_exe, tmp_path, policy):
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
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy))
    result = mdf(python_exe, "delivery", "record", "--repo", str(work), "--stage", "design",
                 "--policy-file", str(path), "--summary", "用户确认接口及验收")
    assert "invalid_policy" in result.stderr or "invalid_delivery_suite" in result.stderr


def test_feature_verify_runs_lint_build_quick_smoke(python_exe, tmp_path):
    repo, root = converge_ready(python_exe, tmp_path)
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    evidence = json.loads((root / "gates/verification.json").read_text())
    assert [item["id"] for item in evidence["results"]] == ["lint", "build", "quick", "smoke"]
    assert [item["budget"] for item in evidence["results"]] == [None, None, 30, 300]
    assert evidence["suites"] == ["quick", "smoke"]
    assert evidence["all_passed"] is True
    evidence["suites"] = ["quick"]
    rewrite_evidence(root, evidence)
    assert "stale_verification" in record(python_exe, repo, "converge").stderr
    evidence["suites"] = ["quick", "smoke"]
    rewrite_evidence(root, evidence)
    payload(record(python_exe, repo, "converge"))
    # 只改预算（不改命令）也必须使全绿证据过期。
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        '  build: "true"', '  build: "true"\n  budgets:\n    quick: 45', 1
    ))
    assert "stale_verification" in record(python_exe, repo, "code-review").stderr


def test_suite_over_budget_fails(python_exe, tmp_path):
    repo, root = converge_ready(python_exe, tmp_path)
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        '  quick: "', '  quick: "sleep 3; ', 1,
    ).replace('  build: "true"', '  build: "true"\n  budgets:\n    quick: 1', 1))
    result = mdf(python_exe, "delivery", "verify", "--repo", str(repo))
    assert "verify_command_failed" in result.stderr
    evidence = json.loads((root / "gates/verification.json").read_text())
    quick = next(item for item in evidence["results"] if item["id"] == "quick")
    assert quick["passed"] is False
    assert quick["budget"] == 1
    assert evidence["all_passed"] is False


@pytest.mark.parametrize(("old", "new"), [
    (f'  smoke: "{SUITE_OK}"\n', ""),
    (f'  smoke: "{SUITE_OK}"', '  smoke: "  "'),
    ('  build: "true"', '  build: "true"\n  commands: []'),
    ('  build: "true"', '  build: "true"\n  full: "true"'),
    ('  build: "true"', '  build: "true"\n  budgets:\n    full: 10'),
    ('  build: "true"', '  build: "true"\n  budgets:\n    lint: 10'),
    ('  build: "true"', '  build: "true"\n  budgets:\n    quick: 0'),
])
def test_manifest_verification_shape(python_exe, tmp_path, old, new):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    manifest = repo / ".mdf/manifest.yaml"
    text = manifest.read_text()
    assert old in text
    manifest.write_text(text.replace(old, new, 1))
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "manifest.verification" in result.stdout


def test_commands_list_manifest_points_to_migrate(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    manifest = repo / ".mdf/manifest.yaml"
    text = manifest.read_text()
    start = text.index("verification:\n")
    end = text.index("implementation_roots:")
    manifest.write_text(
        text[:start]
        + 'verification:\n  commands:\n    - id: check\n      kind: custom\n      command: "true"\n'
        + text[end:]
    )
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "manifest.verification" in result.stdout
    assert "$mdf migrate" in result.stdout


def test_manifest_accepts_budget_overrides(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        '  build: "true"', '  build: "true"\n  budgets:\n    quick: 45\n    release: 3600', 1
    ))
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))
