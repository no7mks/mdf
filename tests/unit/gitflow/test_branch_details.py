"""Gitflow 分支名的分类与交付 slug。"""
from mdf_test_support import *  # noqa: F403


def core():
    load_core_module()
    from mdf_core import gitutil
    from mdf_core.errors import MDFError
    return gitutil, MDFError


@pytest.mark.parametrize(("name", "kind", "slug", "version"), [
    ("feature/Service_Health", "feature", "service-health", None),
    ("bugfix/bug-CD34", "bugfix", "bug-cd34", None),
    ("release/1.3.0", "release", "1-3-0", "1.3.0"),
    ("hotfix/1.2.1", "hotfix", "1-2-1", "1.2.1"),
])
def test_delivery_branches(name, kind, slug, version):
    gitutil, _ = core()
    details = gitutil.branch_details(name)
    assert (details["kind"], details["slug"], details["version"], details["supported"]) == (
        kind, slug, version, True,
    )


@pytest.mark.parametrize("name", ["develop", "master", "planning", "qa/feature/x/1"])
def test_other_branches_are_unsupported(name):
    gitutil, _ = core()
    assert gitutil.branch_details(name)["kind"] == "unsupported"


@pytest.mark.parametrize("name", ["release/1.3", "hotfix/1.3.0-rc.1", "release/v1.3.0"])
def test_release_branches_require_stable_semver(name):
    gitutil, MDFError = core()
    with pytest.raises(MDFError) as error:
        gitutil.branch_details(name)
    assert error.value.code == "bad_release_branch"
