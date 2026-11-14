"""workflow 配置解析：缺省、校验与保留名冲突。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from support_github_flow import github_flow_repo, set_workflow

load_core_module()
from mdf_core.foundation.errors import MDFError  # noqa: E402
from mdf_core.workspace import workflow_policy as wp  # noqa: E402


def test_missing_workflow_defaults_to_gitflow_master():
    assert wp.parse_workflow({}) == {"model": "gitflow", "trunk": "master"}


@pytest.mark.parametrize("trunk", ["main", "trunk", "stable/2026", "prod"])
def test_any_legal_trunk_is_accepted(trunk):
    got = wp.parse_workflow({"workflow": {"model": "github-flow", "trunk": trunk}})
    assert got == {"model": "github-flow", "trunk": trunk}


@pytest.mark.parametrize("trunk", [
    "develop", "planning", "feature/x", "bugfix/x", "release/1.0.0", "on-demand-release/1.0.0",
    "hotfix/x", "support/1.2", "adhoc/x", "qa/x", "dev/x", "codex/x",
])
def test_reserved_trunk_names_are_rejected(trunk):
    with pytest.raises(MDFError) as caught:
        wp.parse_workflow({"workflow": {"model": "github-flow", "trunk": trunk}})
    assert caught.value.code == "invalid_workflow"


@pytest.mark.parametrize("raw", [
    {"model": "svn"}, {"trunk": ""}, {"trunk": "a..b"}, {"trunk": "-x"}, {"trunk": 3},
    {"model": "gitflow", "extra": 1}, "github-flow", [],
])
def test_invalid_workflow_is_rejected(raw):
    with pytest.raises(MDFError) as caught:
        wp.parse_workflow({"workflow": raw})
    assert caught.value.code == "invalid_workflow"


def test_null_workflow_is_rejected():
    with pytest.raises(MDFError):
        wp.parse_workflow({"workflow": None})


def test_resolution_helpers_follow_manifest(tmp_path):
    repo = github_flow_repo(tmp_path, trunk="main")
    assert wp.is_github_flow(repo)
    assert wp.trunk_branch(repo) == "main"
    assert wp.integration_branch(repo) == "main"
    assert wp.permanent_trunks(repo) == ("main",)
    with pytest.raises(MDFError) as caught:
        wp.require_gitflow(repo, "to develop")
    assert caught.value.code == wp.GITHUB_FLOW_UNSUPPORTED


def test_gitflow_helpers_keep_develop_and_planning(tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    assert not wp.is_github_flow(repo)
    assert wp.integration_branch(repo) == "develop"
    assert wp.permanent_trunks(repo) == ("master", "develop", "planning")
    wp.require_gitflow(repo, "to develop")


def test_github_flow_pr_mode_has_short_lived_planning(tmp_path):
    repo = github_flow_repo(tmp_path, pr=True)
    assert wp.permanent_trunks(repo) == ("master", "planning")


@pytest.mark.parametrize("name", ["main", "trunk", "production", "support/1.2"])
def test_occupies_delivery_excludes_custom_trunk_and_support(name):
    from mdf_core.workspace.gitutil import occupies_delivery
    assert occupies_delivery(name) is False


@pytest.mark.parametrize("name", ["feature/x", "qa/1", "dev/1", "codex/integrate/release-1.2.0"])
def test_occupies_delivery_keeps_explicit_delivery_prefixes(name):
    from mdf_core.workspace.gitutil import occupies_delivery
    assert occupies_delivery(name, "production") is True
    assert occupies_delivery("production", "production") is False
