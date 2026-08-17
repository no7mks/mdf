"""Proposal 直接依赖的契约校验。"""

from __future__ import annotations

import pytest

from mdf_test_support import *  # noqa: F403


PRP_ID = "prp-01arz3ndektsv4rrffq69g5fav"
DEPENDENCY_ID = "prp-01arz3ndektsv4rrffq69g5fax"


def write_proposal(
    repo: Path, identifier: str, slug: str, related: str = "[]"
) -> Path:
    source = repo / "proposals" / PRP_NAME
    target = repo / "proposals" / f"{identifier}-{slug}.md"
    target.write_text(
        source.read_text(encoding="utf-8")
        .replace(PRP_ID, identifier)
        .replace("status: ready", "status: draft")
        .replace("related: []", f"related: {related}"),
        encoding="utf-8",
    )
    return target


def validation_codes(python_exe: str, repo: Path) -> set[str]:
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    return {item["code"] for item in json.loads(result.stdout)["findings"]}


def test_proposal_accepts_direct_active_proposal_dependency(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    write_proposal(repo, DEPENDENCY_ID, "health-client", f"[{PRP_ID}]")
    init_git(repo)

    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


@pytest.mark.parametrize(
    ("dependency", "expected_code"),
    [
        ("prp-01arz3ndektsv4rrffq69g5fay", "object.related_missing"),
        (BUG_ID, "proposal.depends_on_type"),
        ("adr-0001", "proposal.depends_on_type"),
    ],
)
def test_proposal_rejects_missing_or_cross_type_dependency(
    python_exe: str,
    tmp_path: Path,
    dependency: str,
    expected_code: str,
):
    repo = copy_fixture(tmp_path)
    if dependency == "adr-0001":
        adr = repo / "docs" / "adr" / "0001-dependency.md"
        adr.parent.mkdir()
        adr.write_text(
            "---\nid: adr-0001\ntype: adr\nstatus: accepted\n---\n\n# ADR\n",
            encoding="utf-8",
        )
    replace(
        repo / "proposals" / PRP_NAME,
        "related: []",
        f"related: [{dependency}]",
    )
    init_git(repo)

    assert expected_code in validation_codes(python_exe, repo)


def test_proposal_rejects_closed_dependency(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    write_proposal(repo, DEPENDENCY_ID, "health-client", f"[{PRP_ID}]")
    replace(
        repo / "proposals" / PRP_NAME,
        "status: ready\nrelated: []",
        "status: closed\nrelated: []\nresolution: rejected",
    )
    init_git(repo)

    assert "proposal.depends_on_inactive" in validation_codes(python_exe, repo)


def test_proposal_rejects_self_dependency(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    replace(
        repo / "proposals" / PRP_NAME,
        "related: []",
        f"related: [{PRP_ID}]",
    )
    init_git(repo)

    assert "proposal.depends_on_self" in validation_codes(python_exe, repo)


def test_proposal_rejects_dependency_cycle(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    write_proposal(repo, DEPENDENCY_ID, "health-client", f"[{PRP_ID}]")
    replace(
        repo / "proposals" / PRP_NAME,
        "related: []",
        f"related: [{DEPENDENCY_ID}]",
    )
    init_git(repo)

    assert "proposal.depends_on_cycle" in validation_codes(python_exe, repo)
