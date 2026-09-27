"""suite 运行的 JUnit XML 报告：解析、失败判定与证据。"""
from mdf_test_support import *  # noqa: F403
from test_mdf_verification_layers import converge_ready

PYTEST_STYLE = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" tests="3">
  <testcase classname="tests.test_a" name="test_one" time="0.25"/>
  <testcase classname="tests.test_a" name="test_two" time="0.5"/>
  <testcase classname="tests.test_b.TestX" name="test_three" time="1"/>
</testsuite></testsuites>
"""


def summarize_dir(tmp_path, files):
    load_core_module()
    from mdf_core.test_reports import summarize
    report = tmp_path / ".mdf/reports/run"
    report.mkdir(parents=True)
    for name, text in files.items():
        (report / name).write_text(text)
    return summarize(tmp_path, report, "quick")


def test_groups_tests_into_cases_by_classname(tmp_path):
    summary = summarize_dir(tmp_path, {"r.xml": PYTEST_STYLE})
    assert summary["tests"] == 3 and summary["passed"] == 3
    assert summary["path"] == ".mdf/reports/run"
    assert summary["cases"] == [
        {"name": "tests.test_a", "result": "passed", "time": 0.75},
        {"name": "tests.test_b.TestX", "result": "passed", "time": 1.0},
    ]
    detail = json.loads((tmp_path / ".mdf/reports/run/summary.json").read_text())
    assert detail["cases"][0]["tests"] == [
        {"name": "test_one", "result": "passed", "time": 0.25},
        {"name": "test_two", "result": "passed", "time": 0.5},
    ]


def test_falls_back_to_suite_name_across_nested_suites(tmp_path):
    xml = ('<testsuites><testsuite name="all"><testsuite name="FooTest">'
           '<testcase name="a"/></testsuite></testsuite></testsuites>')
    summary = summarize_dir(tmp_path, {"r.xml": xml})
    assert summary["cases"] == [{"name": "FooTest", "result": "passed", "time": None}]


@pytest.mark.parametrize(("files", "code"), [
    ({}, "missing_test_report"),
    ({"r.xml": "<testsuites/>"}, "empty_test_report"),
    ({"r.xml": "<testsuite"}, "invalid_test_report"),
    ({"r.xml": '<testsuite name="c"><testcase name="t"><skipped/></testcase></testsuite>'},
     "test_report_failed"),
    ({"r.xml": '<testsuite name="c"><testcase name="t"><failure/></testcase></testsuite>'},
     "test_report_failed"),
    ({"r.xml": '<testsuite name="c"><testcase name="t"><error/></testcase></testsuite>'},
     "test_report_failed"),
])
def test_report_failures(tmp_path, files, code):
    load_core_module()
    from mdf_core.errors import MDFError
    with pytest.raises(MDFError) as error:
        summarize_dir(tmp_path, files)
    assert error.value.code == code


def test_verify_records_suite_reports_and_rejects_skipped(python_exe, tmp_path):
    repo, root = converge_ready(python_exe, tmp_path)
    payload(mdf(python_exe, "delivery", "verify", "--repo", str(repo)))
    evidence = json.loads((root / "gates/verification.json").read_text())
    reports = {item["id"]: item.get("report") for item in evidence["results"]}
    assert reports["lint"] is None and reports["build"] is None
    assert reports["quick"]["suite"] == "quick" and reports["smoke"]["tests"] == 1
    assert (repo / reports["smoke"]["path"] / "r.xml").is_file()
    assert ".mdf/" not in git(repo, "status", "--porcelain").stdout
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        SUITE_OK, SUITE_OK.replace("<testcase/>", "<testcase><skipped/></testcase>"), 1,
    ))
    result = mdf(python_exe, "delivery", "verify", "--repo", str(repo))
    assert "verify_command_failed" in result.stderr
    evidence = json.loads((root / "gates/verification.json").read_text())
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
