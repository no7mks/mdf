"""modules.yaml 解析与 ⊆ 校验。"""
from pathlib import Path

from mdf_test_support import *  # noqa: F403


def test_parse_modules_and_union_commands():
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
    assert v.commands["lint"] == "lint-a && lint-b"
    assert config.named_owner()["widget"] == "b"
    assert config.modules_for_paths(
        Path("."), ["a/src/main.py", "b/src/gen/x.py"]
    ) == ["a"]
