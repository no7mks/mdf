"""JUnit XML 报告的解析、分组与失败判定。"""
from mdf_test_support import *  # noqa: F403


PYTEST_STYLE = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" tests="3">
  <testcase classname="tests.test_a" name="test_one" time="0.25"/>
  <testcase classname="tests.test_a" name="test_two" time="0.5"/>
  <testcase classname="tests.test_b.TestX" name="test_three" time="1"/>
</testsuite></testsuites>
"""


def summarize_dir(tmp_path, files):
    load_core_module()
    from mdf_core.execution.reports import summarize
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
    from mdf_core.foundation.errors import MDFError
    with pytest.raises(MDFError) as error:
        summarize_dir(tmp_path, files)
    assert error.value.code == code
