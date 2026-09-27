"""branch 命令对 Gitflow 分支的分类。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize(
    ("branch", "kind", "slug", "version"),
    [
        ("feature/api/user_auth", "feature", "api-user-auth", None),
        ("bugfix/timeout-fix", "bugfix", "timeout-fix", None),
        ("release/1.4.0", "release", None, "1.4.0"),
        ("hotfix/1.4.1", "hotfix", None, "1.4.1"),
    ],
)
def test_gitflow_branch_classification(
    python_exe: str,
    branch: str,
    kind: str,
    slug: str | None,
    version: str | None,
):
    data = payload(mdf(python_exe, "branch", "--name", branch))
    assert data["kind"] == kind
    if slug is not None:
        assert data["slug"] == slug
    if version is not None:
        assert data["version"] == version


@pytest.mark.parametrize(
    "branch",
    [
        "release/1.2",
        "release/1.2.3-rc.1",
        "hotfix/0.0.0-unreleased",
    ],
)
def test_non_delivery_or_invalid_version_branch_is_rejected(
    python_exe: str, branch: str
):
    result = mdf(python_exe, "branch", "--name", branch)
    assert result.returncode != 0
    assert "bad_release_branch" in result.stderr


@pytest.mark.parametrize("branch", ["main", "develop", "feature/"])
def test_non_delivery_branch_is_classified_as_unsupported(
    python_exe: str, branch: str
):
    data = payload(mdf(python_exe, "branch", "--name", branch))
    assert data["supported"] is False
    assert data["kind"] == "unsupported"


def test_branch_reads_current_git_branch(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "checkout", "-b", "bugfix/unreleased-timeout")

    data = payload(mdf(python_exe, "branch", "--repo", str(repo)))
    assert data["kind"] == "bugfix"
    assert data["slug"] == "unreleased-timeout"
