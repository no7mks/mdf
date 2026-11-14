"""catch-up-plan 的纯函数：路径分类与 depends_on 反向传递。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403

load_core_module()
from mdf_core.execution.modules import parse_modules  # noqa: E402
from mdf_core.foundation.yamlutil import parse_yaml  # noqa: E402
from mdf_core.lifecycle.catchup_plan import classify, dependents  # noqa: E402


@pytest.mark.parametrize("path,kind", [
    ("src/a.py", "code"), ("GLOSSARY.md", "fact"), ("docs/system/interfaces/api.md", "fact"),
    ("docs/user-guide/README.md", "fact"), ("docs/proposals/x.md", "material"),
    ("changes/unreleased/x/objectives.md", "material"), ("README.md", "material"),
    ("src/objectives.md", "material"), ("tests/test_a.py", "code"),
])
def test_classify(path, kind):
    assert classify(path) == kind


def module(name, depends=""):
    return (f"  {name}:\n    sourceset: ['{name}/**']\n    ignore: []\n    lint: 'true'\n    build: 'true'\n"
            + "".join(f"    {s}:\n      command: 'true'\n      tests: ['t/**']\n" for s in ("quick", "smoke", "release"))
            + "    named: []\n" + (f"    depends_on: [{depends}]\n" if depends else ""))


def test_dependents_follow_depends_on_transitively_and_default_to_touched():
    flat = parse_modules(parse_yaml("modules:\n" + module("a") + module("b")))
    assert dependents(flat, {"a"}) == ["a"]
    chain = parse_modules(parse_yaml("modules:\n" + module("a") + module("b", "a") + module("c", "b") + module("d")))
    assert dependents(chain, {"a"}) == ["a", "b", "c"]
    assert dependents(chain, {"d"}) == ["d"]
