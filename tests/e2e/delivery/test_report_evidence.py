"""suite 报告写入 verify.full 证据，以及 suite-run 对 named suite 的运行。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import *  # noqa: F403


def test_verify_records_suite_reports_and_rejects_skipped(python_exe, tmp_path):
    repo, root = converge_ready(python_exe, tmp_path)
    payload(mdf(python_exe, "project-verify", "run", "--repo", str(repo)))
    evidence = json.loads((root / "verify.full.json").read_text())
    reports = {item["id"]: item.get("report") for item in evidence["results"]}
    assert reports["lint"] is None and reports["build"] is None
    assert reports["quick"]["suite"] == "quick" and reports["smoke"]["tests"] == 1
    assert (repo / reports["smoke"]["path"] / "r.xml").is_file()
    assert ".mdf/" not in git(repo, "status", "--porcelain").stdout
    patch_module_command(
        repo,
        "quick",
        lambda c: c.replace("<testcase/>", "<testcase><skipped/></testcase>"),
    )
    commit(repo, "test: quick 含 skipped")
    result = mdf(python_exe, "project-verify", "run", "--repo", str(repo))
    assert "verify_command_failed" in result.stderr
    evidence = json.loads((root / "verify.full.json").read_text())
    quick = next(item for item in evidence["results"] if item["id"] == "quick")
    assert quick["passed"] is False and quick["error"] == "test_report_failed"
    assert quick["details"]["report"]["skipped"] == 1


def test_suite_run_reports_named_suite(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = payload(mdf(python_exe, "suite-run", "--repo", str(repo),
                         "--name", "billing", "--command", SUITE_OK))
    assert result["result"]["report"]["suite"] == "billing"
    assert result["result"]["report"]["path"].startswith(".mdf/reports/")
    assert result["result"]["report"]["path"].endswith("-billing")
    reserved = mdf(python_exe, "suite-run", "--repo", str(repo),
                   "--name", "full", "--command", SUITE_OK)
    assert "invalid_delivery_suite" in reserved.stderr
    missing = mdf(python_exe, "suite-run", "--repo", str(repo),
                  "--name", "billing", "--command", "true")
    assert "missing_test_report" in missing.stderr
