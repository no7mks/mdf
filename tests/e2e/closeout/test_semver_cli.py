"""semver-check 对稳定版本与所需递增的判定。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


@pytest.mark.parametrize(
    "version",
    [
        "1.2",
        "version-1.2.3",
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2.3-rc.1",
        "1.2.3+build",
        "0.0.0-unreleased",
    ],
)
def test_release_versions_are_strict_stable_semver(
    python_exe: str, version: str
):
    result = mdf(
        python_exe,
        "semver-check",
        "--previous",
        "1.2.2",
        "--candidate",
        version,
        "--categories",
        "Fixed",
    )
    assert result.returncode != 0
    assert "invalid_semver" in result.stderr


@pytest.mark.parametrize(
    ("previous", "candidate", "categories", "breaking", "expected_ok"),
    [
        ("1.2.3", "1.2.4", "Fixed", False, True),
        ("1.2.3", "1.2.4", "Added", False, False),
        ("1.2.3", "1.3.0", "Added,Fixed", False, True),
        ("1.2.3", "2.0.0", "Added", False, True),
        ("1.2.3", "1.3.0", "Changed", True, False),
        ("1.2.3", "2.0.0", "Changed", True, True),
        ("1.2.3", "1.3.0", "Removed", False, False),
        ("1.2.3", "2.0.0", "Removed", False, False),
        ("0.2.7", "0.2.8", "Fixed", True, False),
        ("0.2.7", "0.3.0", "Fixed", True, True),
    ],
)
def test_minimum_semver_bump(
    python_exe: str,
    previous: str,
    candidate: str,
    categories: str,
    breaking: bool,
    expected_ok: bool,
):
    args = [
        "semver-check",
        "--previous",
        previous,
        "--candidate",
        candidate,
        "--categories",
        categories,
    ]
    if breaking:
        args.append("--breaking")
    result = mdf(python_exe, *args)
    assert (result.returncode == 0) is expected_ok, (
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_removed_category_requires_explicit_breaking_flag(python_exe: str):
    rejected = mdf(
        python_exe,
        "semver-check",
        "--previous",
        "1.2.3",
        "--candidate",
        "2.0.0",
        "--categories",
        "Removed",
    )
    assert rejected.returncode != 0
    assert (
        payload(
            mdf(
                python_exe,
                "semver-check",
                "--previous",
                "1.2.3",
                "--candidate",
                "2.0.0",
                "--categories",
                "Removed",
                "--breaking",
            )
        )["breaking_declared"]
        is True
    )
