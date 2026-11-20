"""启动入口只接受当前交付种类与参数，发布和维护线参数仍可用。"""
import pytest

from mdf_test_support import load_core_module

load_core_module()
from mdf_core.cli import build_parser


@pytest.mark.parametrize("extra", [
    ["--from-master"], ["--target", "develop"], ["--feature", "feature/work"],
    ["--scope-file", "scope.json"], ["--kind", "on-demand-release"],
])
def test_start_rejects_removed_routing_arguments(extra):
    with pytest.raises(SystemExit) as caught:
        build_parser().parse_args(["start", "--repo", "/repo", "--kind", "feature", *extra])
    assert caught.value.code == 2


@pytest.mark.parametrize("action", ["target", "checkpoint", "scope", "accept"])
def test_delivery_rejects_removed_actions(action):
    with pytest.raises(SystemExit) as caught:
        build_parser().parse_args(["delivery", action, "--repo", "/repo"])
    assert caught.value.code == 2


@pytest.mark.parametrize("kind,option,value,field", [
    ("release", "--from-commit", "a" * 40, "from_commit"),
    ("hotfix", "--support", "1.2", "support"),
])
def test_release_cutpoint_and_support_options_remain(kind, option, value, field):
    args = build_parser().parse_args(["start", "--repo", "/repo", "--kind", kind, option, value])
    assert getattr(args, field) == value
