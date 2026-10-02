"""modules.yaml 解析与按 module 串行展开。"""
from pathlib import Path

from mdf_test_support import *  # noqa: F403


def test_parse_modules_expands_plan_per_module():
    load_core_module()
    from mdf_core.modules import parse_modules

    config = parse_modules(
        {
            "modules": {
                "a": {
                    "sourceset": ["a/src/**"],
                    "ignore": [],
                    "lint": "lint-a",
                    "build": "build-a",
                    "quick": {"command": "q-a", "tests": ["a/tests/**"]},
                    "smoke": {"command": "s-a", "tests": ["a/tests/**"]},
                    "release": {"command": "r-a", "tests": ["a/tests/**"]},
                    "named": [],
                },
                "b": {
                    "sourceset": ["b/src/**"],
                    "ignore": [{"pattern": "b/src/gen/**", "reason": "generated"}],
                    "lint": "lint-b",
                    "build": "build-b",
                    "quick": {"command": "q-b", "tests": ["b/tests/**"]},
                    "smoke": {"command": "s-b", "tests": ["b/tests/**"]},
                    "release": {"command": "r-b", "tests": ["b/tests/**"]},
                    "named": ["widget"],
                },
            }
        }
    )
    assert config.names() == ["a", "b"]
    v = config.verification()
    assert [item["id"] for item in v.plan("smoke")] == [
        "lint:a", "lint:b", "build:a", "build:b",
        "quick:a", "quick:b", "smoke:a", "smoke:b",
    ]
    assert [item["command"] for item in v.plan("smoke")] == [
        "lint-a", "lint-b", "build-a", "build-b",
        "q-a", "q-b", "s-a", "s-b",
    ]
    assert config.named_owner()["widget"] == "b"
    assert config.modules_for_paths(
        Path("."), ["a/src/main.py", "b/src/gen/x.py"]
    ) == ["a"]


def test_repo_verification_override_keeps_other_entries_expanded():
    load_core_module()
    from mdf_core.modules import parse_modules

    config = parse_modules(
        {
            "verification": {"lint": "make -j1 lint"},
            "modules": {
                "a": {
                    "sourceset": ["a/src/**"],
                    "ignore": [],
                    "lint": "lint-a",
                    "build": "build-a",
                    "quick": {"command": "q-a", "tests": ["a/tests/**"]},
                    "smoke": {"command": "s-a", "tests": ["a/tests/**"]},
                    "release": {"command": "r-a", "tests": ["a/tests/**"]},
                    "named": [],
                },
                "b": {
                    "sourceset": ["b/src/**"],
                    "ignore": [],
                    "lint": "lint-b",
                    "build": "build-b",
                    "quick": {"command": "q-b", "tests": ["b/tests/**"]},
                    "smoke": {"command": "s-b", "tests": ["b/tests/**"]},
                    "release": {"command": "r-b", "tests": ["b/tests/**"]},
                    "named": [],
                },
            },
        }
    )
    v = config.verification()
    assert [item["id"] for item in v.plan("quick")] == [
        "lint", "build:a", "build:b", "quick:a", "quick:b",
    ]
    assert v.plan("quick")[0]["command"] == "make -j1 lint"
    assert v.config()["overrides"] == {"lint": "make -j1 lint"}


def test_invalid_verification_override_keys():
    load_core_module()
    from mdf_core.errors import MDFError
    from mdf_core.modules import parse_modules

    with pytest.raises(MDFError) as error:
        parse_modules(
            {
                "verification": {"full": "x"},
                "modules": {
                    "a": {
                        "sourceset": ["a/**"],
                        "lint": "l",
                        "build": "b",
                        "quick": {"command": "q", "tests": ["a/**"]},
                        "smoke": {"command": "s", "tests": ["a/**"]},
                        "release": {"command": "r", "tests": ["a/**"]},
                    }
                },
            }
        )
    assert error.value.code == "modules_invalid"
