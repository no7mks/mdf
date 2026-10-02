"""bug close 的状态写入、版本校验与失败不写入。"""
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize("branch", ["feature/accept-fix", "release/1.3.0", "hotfix/1.3.0"])
def test_bug_close_writes_status_and_version(python_exe, tmp_path, branch):
    repo = copy_fixture(tmp_path)
    bug = repo / "docs/bugs" / BUG_NAME
    replace(bug, "status: open", 'status: "fixed" # verified by intent')
    init_git(repo)
    git(repo, "checkout", "-b", branch)
    result = payload(mdf(
        python_exe, "bug", "close", BUG_ID, "--fixed-in", "1.3.0", "--repo", str(repo),
    ))
    assert result["status"] == "closed" and result["fixed_in"] == "1.3.0"
    text = bug.read_text()
    assert "status: closed" in text and "fixed_in: 1.3.0" in text
    assert "found_in: unreleased" in text
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full"))


@pytest.mark.parametrize("version", ["unreleased", "1.3.0-rc.1", "1.2.1"])
def test_bug_close_rejects_invalid_or_mismatched_version(python_exe, tmp_path, version):
    repo = copy_fixture(tmp_path)
    bug = repo / "docs/bugs" / BUG_NAME
    replace(bug, "status: open", "status: fixed")
    init_git(repo)
    git(repo, "checkout", "-b", "release/1.3.0")
    before = bug.read_text()
    result = mdf(
        python_exe, "bug", "close", BUG_ID, "--fixed-in", version, "--repo", str(repo),
    )
    assert result.returncode != 0 and "invalid_fixed_in" in result.stderr
    assert bug.read_text() == before


@pytest.mark.parametrize("status", ["open", "closed", "rejected"])
def test_bug_close_requires_fixed_state(python_exe, tmp_path, status):
    repo = copy_fixture(tmp_path)
    bug = repo / "docs/bugs" / BUG_NAME
    replace(bug, "status: open", f"status: {status}")
    init_git(repo)
    before = bug.read_text()
    result = mdf(
        python_exe, "bug", "close", BUG_ID, "--fixed-in", "1.3.0", "--repo", str(repo),
    )
    assert result.returncode != 0 and "bug_not_fixed" in result.stderr
    assert bug.read_text() == before


def test_bug_close_requires_version(python_exe, tmp_path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = mdf(python_exe, "bug", "close", BUG_ID, "--repo", str(repo))
    assert result.returncode != 0 and "--fixed-in" in result.stderr
