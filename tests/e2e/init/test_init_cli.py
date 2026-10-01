"""init 的验证入口参数与 prepare-git。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_modules_required_while_ready(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    (repo / ".mdf" / "modules.yaml").unlink()
    replace(
        repo / ".mdf" / "manifest.yaml", "state: ready", "state: initializing"
    )
    init_git(repo)

    targeted = mdf(python_exe, "validate", "--repo", str(repo))
    assert targeted.returncode != 0
    assert "manifest.initializing" in targeted.stdout
    assert "modules.missing" in targeted.stdout

    replace(
        repo / ".mdf" / "manifest.yaml", "state: initializing", "state: ready"
    )
    ready = mdf(python_exe, "validate", "--repo", str(repo))
    assert ready.returncode != 0
    assert "modules.missing" in ready.stdout


def test_init_requires_a_non_empty_verification_command(
    python_exe: str, tmp_path: Path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    init_git(repo)
    result = mdf(
        python_exe,
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "none",
        *all_not_applicable_baselines(),
    )

    assert result.returncode != 0
    assert "--lint" in result.stderr

    empty = mdf(
        python_exe,
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "none",
        *all_not_applicable_baselines(),
        *verification_args(),
        "--smoke",
        "  ",
    )
    assert empty.returncode != 0
    assert "invalid_verification" in empty.stderr

    budget = mdf(
        python_exe,
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "none",
        *all_not_applicable_baselines(),
        *verification_args(),
        "--budget",
        "lint=10",
    )
    assert budget.returncode != 0
    assert "invalid_verification" in budget.stderr


def test_prepare_git_inits_plain_directory_and_skips_existing_root(
    python_exe: str, tmp_path: Path
):
    plain = tmp_path / "plain"
    plain.mkdir()
    created = payload(mdf(python_exe, "prepare-git", "--repo", str(plain)))
    assert created["created"] is True
    assert created["branch"] == "master"
    assert (plain / ".git").is_dir()

    skipped = payload(mdf(python_exe, "prepare-git", "--repo", str(plain)))
    assert skipped["created"] is False
    assert skipped["branch"] == "master"

    nested = plain / "child"
    nested.mkdir()
    result = mdf(python_exe, "prepare-git", "--repo", str(nested))
    assert result.returncode != 0
    assert "nested_git" in result.stderr
