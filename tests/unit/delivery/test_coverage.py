"""Coverage 可选配置、精确阈值和统一报告失败语义。"""
import json

import pytest

from mdf_core.execution.coverage import parse_coverage, summarize_coverage
from mdf_core.execution.modules import parse_modules
from mdf_core.foundation.errors import MDFError


def configuration(coverage=None):
    module = {"sourceset": ["src/**"], "lint": "true", "build": "true",
              **{name: {"command": "test", "tests": ["tests/**"]} for name in ("quick", "smoke", "release")}}
    if coverage is not None:
        module["coverage"] = coverage
    return {"modules": {"app": module}}


def test_optional_coverage_and_repo_override_do_not_change_branch_plan():
    raw = configuration()
    assert parse_modules(raw).verification()._items_for_entry("coverage") == []
    raw["modules"]["app"]["coverage"] = {"command": "per-module", "targets": {"lines": 80}}
    raw["verification"] = {"coverage": {"command": "whole-repo", "targets": {"branches": 75}}}
    plan = parse_modules(raw).verification()
    assert plan._items_for_entry("coverage") == [{
        "id": "coverage", "entry": "coverage", "command": "whole-repo",
        "coverage_targets": {"branches": 75}, "budget": None,
    }]
    assert all(item["entry"] != "coverage" for item in plan.plan("release"))


@pytest.mark.parametrize("targets", [{}, {"lines": -1}, {"lines": 101}, {"lines": True},
                                     {"lines": "85"}, {"": 80}, {"lines": float("nan")},
                                     {"lines": float("inf")}, {"lines": 10**400}])
def test_invalid_coverage_targets(targets):
    with pytest.raises(MDFError, match="targets"):
        parse_coverage({"command": "check", "targets": targets}, "coverage")


@pytest.mark.parametrize("raw", [None, "check", {}, {"command": "check"},
                                 {"command": " ", "targets": {"lines": 80}}])
def test_invalid_coverage_definition(raw):
    with pytest.raises(MDFError):
        parse_coverage(raw, "coverage")


def test_coverage_is_reserved_for_named_suite():
    raw = configuration()
    raw["modules"]["app"]["named"] = ["coverage"]
    with pytest.raises(MDFError, match="named"):
        parse_modules(raw)


def test_reserved_coverage_error_identifies_the_reserved_entry():
    from mdf_core.execution.verification import parse_suite_names

    with pytest.raises(MDFError, match="coverage"):
        parse_suite_names(["coverage"])


def test_all_metrics_must_pass_and_threshold_is_not_rounded(tmp_path):
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps({"metrics": {"lines": {"covered": 84999, "total": 100000},
                                             "branches": {"covered": 3, "total": 4}}}))
    with pytest.raises(MDFError) as error:
        summarize_coverage(tmp_path, {"lines": 85, "branches": 75})
    assert error.value.details["metrics"]["lines"]["passed"] is False
    assert error.value.details["metrics"]["branches"]["passed"] is True
    result = summarize_coverage(tmp_path, {"lines": 84.999, "branches": 75})
    assert result["all_passed"] is True
    assert json.loads((tmp_path / "summary.json").read_text()) == result


@pytest.mark.parametrize("data", [None, "invalid", {}, {"metrics": {}},
                                  {"metrics": {"lines": {"covered": 0, "total": 0}}},
                                  {"metrics": {"lines": {"covered": 2, "total": 1}}},
                                  {"metrics": {"lines": {"covered": True, "total": 1}}},
                                  {"metrics": {"lines": {"covered": 0.5, "total": 1}}}])
def test_missing_or_invalid_report_is_persisted_as_failure(tmp_path, data):
    if data is not None:
        (tmp_path / "coverage.json").write_text(data if isinstance(data, str) else json.dumps(data))
    with pytest.raises(MDFError):
        summarize_coverage(tmp_path, {"lines": 80})
    assert json.loads((tmp_path / "summary.json").read_text())["all_passed"] is False
