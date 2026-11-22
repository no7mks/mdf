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
    obj.write_text("# 目标\n\n- needs_design: yes\n\n实现健康状态接口。\n")
    data = payload(mdf(python_exe, "start", "--repo", str(repo), "--kind", "feature",
                       "--proposal", "prp-0001", "--objectives-file", str(obj)))
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


def test_feature_verify_branch_runs_lint_build_quick_smoke(python_exe, tmp_path):
    """feature 的 verify branch 默认 suite 为 smoke。"""
    repo, root = converge_ready(python_exe, tmp_path)
    payload(mdf(python_exe, "verify", "--scope", "branch", "--repo", str(repo)))
    evidence = json.loads((root / "verification-report.json").read_text())
    assert [item["id"] for item in evidence["results"]] == [
        "lint:default", "build:default", "quick:default", "smoke:default",
    ]
    assert [item["budget"] for item in evidence["results"]] == [
        None, None, 30, 500,
    ]
    assert evidence["suites"] == ["quick", "smoke"]
    assert evidence["all_passed"] is True
    payload(record(python_exe, repo, "converge"))
    assert not (root / "gates/code-review.json").exists()


def test_suite_over_budget_fails(python_exe, tmp_path):
    repo, root = converge_ready(python_exe, tmp_path)
    patch_module_command(repo, "quick", lambda c: "sleep 3; " + c)
    set_modules_budget(repo, "quick", 1)
    commit(repo, "test: quick 超预算")
    result = mdf(python_exe, "verify", "--scope", "branch", "--repo", str(repo))
    assert "verify_command_failed" in result.stderr
    evidence = json.loads((root / "verification-report.json").read_text())
    quick = next(
        item for item in evidence["results"] if item["id"] == "quick:default"
    )
    assert quick["passed"] is False
    assert quick["budget"] == 1
    assert evidence["all_passed"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.replace(
            '      command: "echo \'<testsuite><testcase/></testsuite>\' > $MDF_REPORT_DIR/r.xml"\n',
            "",
            1,
        ),
        lambda t: t.replace("    lint: \"true\"", "    lint: \"  \""),
        lambda t: t + "\n  extra: true\n",
        lambda t: t.replace("budgets:\n", "budgets:\n  full: 10\n")
        if "budgets:" in t
        else t + "\nbudgets:\n  full: 10\n",
        lambda t: t + "\nbudgets:\n  lint: 10\n",
        lambda t: t + "\nbudgets:\n  quick: 0\n",
    ],
)
def test_modules_verification_shape(python_exe, tmp_path, mutate):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    path = modules_yaml(repo)
    path.write_text(mutate(path.read_text()))
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "modules.invalid" in result.stdout or "modules." in result.stdout


def test_manifest_verification_moved_finding(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    manifest = repo / ".mdf/manifest.yaml"
    text = manifest.read_text()
    manifest.write_text(
        text.replace(
            "implementation_roots:",
            'verification:\n  lint: "true"\n  build: "true"\n'
            f'  quick: "{SUITE_OK}"\n  smoke: "{SUITE_OK}"\n'
            f'  release: "{SUITE_OK}"\nimplementation_roots:',
            1,
        )
    )
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert "manifest.verification_moved" in result.stdout
    assert "$mdf migrate" in result.stdout


def test_modules_accepts_budget_overrides(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    set_modules_budget(repo, "quick", 45)
    set_modules_budget(repo, "release", 3600)
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))
