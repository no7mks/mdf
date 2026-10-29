"""全成员已知 Bug 豁免必须有本轮 collection 和有效关联证据。"""
import json
import shlex
import sys

from mdf_test_support import *  # noqa: F403


def prepare(tmp_path):
    load_core_module()
    report = tmp_path / ".mdf/reports/run"
    report.mkdir(parents=True)
    (report / "junit.xml").write_text('<testsuite name="empty" tests="0"/>')
    test = tmp_path / "tests/test_bug.py"
    test.parent.mkdir()
    test.write_text("def test_bug(): assert False\n")
    identity = {"module": "app", "file": "tests/test_bug.py", "test_id": "tests/test_bug.py::test_bug"}
    bug = tmp_path / "docs/bugs/bug-AB12-example.md"
    bug.parent.mkdir(parents=True)
    link = {**identity, "suites": ["quick", "smoke"], "state": "removed"}
    write_bug(bug, link)
    evidence = {"suite": "quick", "collected": [identity],
                "excluded": [{**identity, "bug": "docs/bugs/bug-AB12-example.md"}]}
    write_evidence(report, evidence)
    return report, bug, link, evidence


def write_bug(bug, link, status="open"):
    bug.write_text(f"---\nid: bug-AB12\ntype: bug\nstatus: {status}\n---\n"
                   "## 所需回归证据\n### 关联 failing tests\n```mdf-test-links\n"
                   + json.dumps([link]) + "\n```\n")


def write_evidence(report, evidence):
    (report / "empty-suite.json").write_text(json.dumps(evidence))


def test_all_excluded_is_accepted_without_inventing_passed_tests(tmp_path):
    report, _, _, evidence = prepare(tmp_path)
    from mdf_core.execution.reports import summarize
    result = summarize(tmp_path, report, "quick")
    assert result["fully_exempted"] is True
    assert result["tests"] == result["passed"] == 0
    assert result["exemptions"] == evidence["excluded"]
    assert json.loads((report / "summary.json").read_text())["fully_exempted"]


@pytest.mark.parametrize("status", ["fixed", "closed", "rejected"])
def test_status_change_invalidates_existing_exemption(tmp_path, status):
    report, bug, link, _ = prepare(tmp_path)
    from mdf_core.execution.reports import summarize
    from mdf_core.foundation.errors import MDFError
    write_bug(bug, link, status)
    with pytest.raises(MDFError, match="open"):
        summarize(tmp_path, report, "quick")


@pytest.mark.parametrize("change", ["uncovered", "duplicate", "empty", "unknown_test", "wrong_suite"])
def test_collection_must_exactly_match_current_bug_links(tmp_path, change):
    report, _, _, evidence = prepare(tmp_path)
    from mdf_core.execution.reports import summarize
    from mdf_core.foundation.errors import MDFError
    if change == "uncovered":
        evidence["collected"].append({**evidence["collected"][0], "test_id": "other"})
    elif change == "duplicate":
        evidence["excluded"] *= 2
    elif change == "empty":
        evidence["collected"] = evidence["excluded"] = []
    elif change == "unknown_test":
        evidence["collected"][0]["test_id"] = "unknown"
        evidence["excluded"][0]["test_id"] = "unknown"
    else:
        evidence["suite"] = "smoke"
    write_evidence(report, evidence)
    with pytest.raises(MDFError):
        summarize(tmp_path, report, "quick")


@pytest.mark.parametrize("suite", ["release", "named"])
def test_release_and_named_cannot_accept_empty_exemption(tmp_path, suite):
    report, _, _, evidence = prepare(tmp_path)
    from mdf_core.execution.reports import summarize
    from mdf_core.foundation.errors import MDFError
    evidence["suite"] = suite
    write_evidence(report, evidence)
    with pytest.raises(MDFError):
        summarize(tmp_path, report, suite)


@pytest.mark.parametrize("state", ["active", "restored"])
def test_only_removed_link_can_explain_empty_suite(tmp_path, state):
    report, bug, link, _ = prepare(tmp_path)
    from mdf_core.execution.reports import summarize
    from mdf_core.foundation.errors import MDFError
    link["state"] = state
    write_bug(bug, link)
    with pytest.raises(MDFError):
        summarize(tmp_path, report, "quick")


@pytest.mark.parametrize("change", ["missing_junit", "invalid_junit", "failure", "missing_proof", "outside_bug"])
def test_exemption_does_not_mask_report_or_evidence_faults(tmp_path, change):
    report, _, _, evidence = prepare(tmp_path)
    from mdf_core.execution.reports import summarize
    from mdf_core.foundation.errors import MDFError
    if change == "missing_junit":
        (report / "junit.xml").unlink()
    elif change == "invalid_junit":
        (report / "junit.xml").write_text("<testsuite")
    elif change == "failure":
        (report / "junit.xml").write_text('<testsuite><testcase name="t"><failure/></testcase></testsuite>')
    elif change == "missing_proof":
        (report / "empty-suite.json").unlink()
    else:
        evidence["excluded"][0]["bug"] = "../outside.md"
        write_evidence(report, evidence)
    with pytest.raises(MDFError):
        summarize(tmp_path, report, "quick")


@pytest.mark.parametrize("exit_code", [0, 1, 5])
def test_command_failure_is_not_hidden_by_full_exemption(tmp_path, exit_code):
    report, _, _, _ = prepare(tmp_path)
    from mdf_core.execution.verify_run import run_verify_command
    from mdf_core.foundation.errors import MDFError
    code = ("import os, pathlib, shutil, sys; "
            "target=pathlib.Path(os.environ['MDF_REPORT_DIR']); "
            f"source=pathlib.Path({str(report)!r}); "
            "shutil.copy(source/'junit.xml', target/'junit.xml'); "
            "shutil.copy(source/'empty-suite.json', target/'empty-suite.json'); "
            f"sys.exit({exit_code})")
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"
    if exit_code:
        with pytest.raises(MDFError) as exc:
            run_verify_command(tmp_path, command, entry="quick", junit=True)
        assert exc.value.details["exit_code"] == exit_code
    else:
        result = run_verify_command(tmp_path, command, entry="quick", junit=True)
        assert result["report"]["fully_exempted"]


@pytest.mark.parametrize("change", ["bug_id", "duplicate_link", "bad_json", "bad_suites", "missing_test", "archived_bug"])
def test_invalid_bug_association_cannot_authorize_empty_suite(tmp_path, change):
    report, bug, link, evidence = prepare(tmp_path)
    from mdf_core.execution.reports import summarize
    from mdf_core.foundation.errors import MDFError
    if change == "bug_id":
        bug.write_text(bug.read_text().replace("id: bug-AB12", "id: bug-CD34"))
    elif change == "duplicate_link":
        bug.write_text(bug.read_text().replace(json.dumps([link]), json.dumps([link, link])))
    elif change == "bad_json":
        bug.write_text(bug.read_text().replace(json.dumps([link]), "invalid"))
    elif change == "bad_suites":
        link["suites"] = "quick"
        write_bug(bug, link)
    elif change == "missing_test":
        (tmp_path / link["file"]).unlink()
    else:
        archive = bug.parent / "archive/1.0" / bug.name
        archive.parent.mkdir(parents=True)
        bug.rename(archive)
        evidence["excluded"][0]["bug"] = str(archive.relative_to(tmp_path))
        write_evidence(report, evidence)
    with pytest.raises(MDFError):
        summarize(tmp_path, report, "quick")


def test_smoke_can_accept_complete_exemptions(tmp_path):
    report, _, _, evidence = prepare(tmp_path)
    from mdf_core.execution.reports import summarize
    evidence["suite"] = "smoke"
    write_evidence(report, evidence)
    assert summarize(tmp_path, report, "smoke")["fully_exempted"]
