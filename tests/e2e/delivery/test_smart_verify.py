"""smart 不依赖交付身份；branch 限制与实际错误仍生效。"""
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize(("branch", "kind", "worktree"), [
    ("develop", "unsupported", False),
    ("master", "unsupported", False),
    ("planning", "unsupported", False),
    ("codex/fix/bug-CD34", "adhoc", True),
    ("qa/feature/service-health/1", "unsupported", False),
    ("dev/feature/service-health/1", "unsupported", False),
    ("临时修复", "adhoc", False),
    ("feature/service-health", "feature", False),
    ("bugfix/bug-CD34", "bugfix", False),
    ("release/1.3.0", "release", False),
    ("hotfix/1.2.1", "hotfix", False),
])
def test_smart_runs_without_delivery_materials(
    python_exe, tmp_path, branch, kind, worktree,
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    if worktree:
        work = tmp_path / "fix"
        git(repo, "worktree", "add", "-b", branch, str(work), "HEAD")
    else:
        git(repo, "checkout", "-b", branch)
        work = repo
    result = payload(mdf(
        python_exe, "verify", "smart", "--repo", str(work),
        "--paths", "src/service.py", "--test", "test -f src/service.py",
    ))["result"]
    assert result["scope"] == "smart"
    assert result["branch"] == branch and result["kind"] == kind
    assert result["modules"] == ["default"]
    assert result["all_passed"] is True
    assert [item["id"] for item in result["results"]] == [
        "lint:default", "build:default", "quick:default", "test:1",
    ]
    assert result["results"][2]["report"]["tests"] == 1
    assert not list(work.rglob("objectives.md"))
    assert not list(work.rglob("delivery.json"))
    assert bool(list(work.rglob("verification-report.json"))) == (kind == "adhoc")


@pytest.mark.parametrize("branch", ["develop", "codex/fix/bug-CD34"])
def test_verify_branch_still_requires_delivery_branch(python_exe, tmp_path, branch):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "checkout", "-b", branch)
    result = mdf(python_exe, "verify", "branch", "--repo", str(repo))
    assert result.returncode != 0
    assert "stage_branch" in result.stderr
    assert not list(repo.rglob("verification-report.json"))


@pytest.mark.parametrize(("branch", "error"), [
    (None, "detached_head"),
    ("release/1.3", "bad_release_branch"),
    ("hotfix/1.3.0-rc.1", "bad_release_branch"),
])
def test_smart_keeps_branch_errors(python_exe, tmp_path, branch, error):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    if branch is None:
        git(repo, "checkout", "--detach", "HEAD")
    else:
        git(repo, "checkout", "-b", branch)
    result = mdf(
        python_exe, "verify", "--scope", "smart", "--repo", str(repo),
        "--module", "default",
    )
    assert result.returncode != 0
    assert error in result.stderr


def test_smart_keeps_module_configuration_errors(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    modules_yaml(repo).write_text("modules: []\n", encoding="utf-8")
    result = mdf(
        python_exe, "verify", "smart", "--repo", str(repo),
        "--module", "default",
    )
    assert result.returncode != 0
    assert "modules_invalid" in result.stderr
