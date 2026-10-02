"""quick-run：任意分支依次运行 lint、build、quick，校验 quick 报告且不写证据。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def error_of(result):
    assert result.returncode != 0
    return json.loads(result.stderr.strip().splitlines()[-1])


def test_quick_run_passes_on_master_and_detached_without_evidence(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    result = payload(mdf(python_exe, "quick-run", "--repo", str(repo)))["result"]
    assert result["all_passed"] is True
    assert result["head"] == git(repo, "rev-parse", "HEAD").stdout.strip()
    assert [item["id"] for item in result["results"]] == [
        "lint:default", "build:default", "quick:default",
    ]
    budgets = {item["id"]: item["budget"] for item in result["results"]}
    assert budgets == {
        "lint:default": None, "build:default": None, "quick:default": 30,
    }
    for item in result["results"]:
        entry = item["id"].split(":", 1)[0]
        assert item["log"].startswith(".mdf/reports/")
        assert item["log"].endswith(f"-{entry}")
        assert (repo / item["log"] / "stdout.log").is_file()
    reports = {item["id"]: item.get("report") for item in result["results"]}
    assert reports["lint:default"] is None and reports["build:default"] is None
    assert reports["quick:default"]["suite"] == "quick"
    assert reports["quick:default"]["tests"] == 1
    assert not (repo / "changes/unreleased").exists() or not list(
        (repo / "changes/unreleased").rglob("*verification.json"))
    assert git(repo, "status", "--porcelain").stdout == ""
    git(repo, "checkout", "--detach")
    payload(mdf(python_exe, "quick-run", "--repo", str(repo)))


def test_quick_run_runs_all_and_reports_every_failure(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    patch_module_command(repo, "build", lambda _: "false")
    patch_module_command(
        repo,
        "quick",
        lambda _: "echo '<testsuite><testcase><skipped/></testcase></testsuite>' > $MDF_REPORT_DIR/r.xml",
    )
    error = error_of(mdf(python_exe, "quick-run", "--repo", str(repo)))
    assert error["error"] == "verify_command_failed"
    details = error["details"]
    assert details["all_passed"] is False
    results = {item["id"]: item for item in details["results"]}
    assert list(results) == ["lint:default", "build:default", "quick:default"]
    assert results["lint:default"]["passed"] is True
    assert results["build:default"]["passed"] is False
    assert results["build:default"]["details"]["exit_code"] == 1
    assert results["quick:default"]["error"] == "test_report_failed"
    assert results["quick:default"]["details"]["report"]["skipped"] == 1


def test_quick_run_rejects_missing_report_and_not_ready(python_exe, tmp_path):
    repo = local_repo(tmp_path)
    patch_module_command(repo, "quick", lambda _: "true")
    error = error_of(mdf(python_exe, "quick-run", "--repo", str(repo)))
    quick = error["details"]["results"][-1]
    assert quick["id"] == "quick:default" and quick["error"] == "missing_test_report"
    replace(repo / ".mdf/manifest.yaml", "state: ready", "state: initializing")
    assert error_of(mdf(python_exe, "quick-run", "--repo", str(repo)))["error"] == "manifest_not_ready"
