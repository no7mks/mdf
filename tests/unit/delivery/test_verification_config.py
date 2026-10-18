"""manifest verification 的校验、执行计划与 suite 选择。"""
from mdf_test_support import *  # noqa: F403

ENTRIES = {"lint": "l", "build": "b", "quick": "q", "smoke": "s", "release": "r"}


def core():
    load_core_module()
    from mdf_core.execution import verification
    from mdf_core.foundation.errors import MDFError
    return verification, MDFError


def test_plan_runs_steps_then_quick_then_target_with_budgets():
    verification, _ = core()
    config = verification.validate_verification({**ENTRIES, "budgets": {"quick": 45}})
    assert [(item["id"], item["budget"]) for item in config.plan("smoke")] == [
        ("lint", None), ("build", None), ("quick", 45), ("smoke", 300),
    ]
    assert [item["id"] for item in config.plan("quick")] == ["lint", "build", "quick"]
    assert config.plan("release")[-1] == {
        "id": "release", "command": "r", "budget": None, "entry": "release",
    }


@pytest.mark.parametrize("raw", [
    None,
    {key: value for key, value in ENTRIES.items() if key != "smoke"},
    {**ENTRIES, "full": "f"},
    {**ENTRIES, "smoke": "  "},
    {**ENTRIES, "budgets": {"lint": 1}},
    {**ENTRIES, "budgets": {"quick": 0}},
    {**ENTRIES, "budgets": {"quick": True}},
])
def test_invalid_verification_shapes(raw):
    verification, MDFError = core()
    with pytest.raises(MDFError) as error:
        verification.validate_verification(raw)
    assert error.value.code == "invalid_verification"


def test_required_suites_by_branch_kind():
    verification, MDFError = core()
    assert verification.required_suites("feature") == ["quick", "smoke"]
    assert verification.required_suites("bugfix") == ["quick", "smoke"]
    assert verification.required_suites("hotfix") == ["quick", "smoke"]
    assert verification.required_suites("release") == ["quick", "release"]
    with pytest.raises(MDFError):
        verification.required_suite("planning")
    assert verification.suites_cover(["quick", "smoke", "x"], ["quick", "smoke"])
    assert not verification.suites_cover(["quick"], ["quick", "smoke"])


@pytest.mark.parametrize("names", [[], ["full"], ["release"], ["Billing"], ["a", "a"], "a"])
def test_named_suite_names_reject_reserved_and_malformed(names):
    verification, MDFError = core()
    with pytest.raises(MDFError) as error:
        verification.parse_suite_names(names)
    assert error.value.code == "invalid_delivery_suite"


def test_budget_arguments():
    verification, MDFError = core()
    assert verification.parse_budgets(["quick=45", "release=900"]) == {
        "quick": 45, "release": 900,
    }
    for raw in (["quick"], ["quick=-1"], ["quick=1", "quick=2"]):
        with pytest.raises(MDFError):
            verification.parse_budgets(raw)
