"""Proposal 直接依赖的契约校验。"""
from __future__ import annotations
import pytest
from mdf_test_support import *  # noqa: F403


PRP_ID = "prp-0001"


DEPENDENCY_ID = "prp-0002"


def write_proposal(
    repo: Path, identifier: str, slug: str, depends_on: str = "[]",
    milestone: str | None = None,
) -> Path:
    source = repo / "docs/proposals" / PRP_NAME
    text = (
        proposal_markdown(source)
        .replace(PRP_ID, identifier)
        .replace("status: ready", "status: draft")
        .replace("depends_on: []", f"depends_on: {depends_on}")
    )
    if milestone is not None:
        text = text.replace(
            f"depends_on: {depends_on}",
            f"depends_on: {depends_on}\n"
            f"milestone: {json.dumps(milestone, ensure_ascii=False)}",
        )
    target = repo / "docs/proposals" / f"{identifier}-{slug}.md"
    target.write_text(text, encoding="utf-8")
    return target


def validation_codes(python_exe: str, repo: Path) -> set[str]:
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    return {item["code"] for item in json.loads(result.stdout)["findings"]}


@pytest.mark.parametrize("identifier", [DEPENDENCY_ID, "prp-002", "prp-10000"])
def test_proposal_accepts_direct_active_proposal_dependency(
    python_exe: str, tmp_path: Path, identifier: str
):
    repo = copy_fixture(tmp_path)
    write_proposal(repo, identifier, "health-client")
    replace(repo / "docs/proposals" / PRP_NAME, "depends_on: []", f"depends_on: [{identifier}]")
    init_git(repo)

    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


@pytest.mark.parametrize(
    ("dependency", "expected_code"),
    [
        (
            "prp-0003",
            "object.depends_on_missing",
        ),
        (BUG_ID, "proposal.depends_on_type"),
        ("adr-dependency", "proposal.depends_on_type"),
    ],
)
def test_proposal_rejects_missing_or_cross_type_dependency(
    python_exe: str,
    tmp_path: Path,
    dependency: str,
    expected_code: str,
):
    repo = copy_fixture(tmp_path)
    if dependency == "adr-dependency":
        adr = repo / "docs" / "context" / "adr" / "dependency.md"
        adr.parent.mkdir(parents=True)
        adr.write_text(
            "---\nid: adr-dependency\ntype: adr\nstatus: accepted\n---\n\n# ADR\n",
            encoding="utf-8",
        )
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "depends_on: []",
        f"depends_on: [{dependency}]",
    )
    init_git(repo)

    assert expected_code in validation_codes(python_exe, repo)


def test_proposal_accepts_released_dependency(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    write_proposal(repo, DEPENDENCY_ID, "health-client", f"[{PRP_ID}]")
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "status: ready\ndepends_on: []",
        (
            "status: released\ndepends_on: []\n"
            "released_in: 1.2.0"
        ),
    )
    init_git(repo)

    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


def test_proposal_accepts_archived_released_dependency(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    write_proposal(repo, DEPENDENCY_ID, "health-client", f"[{PRP_ID}]")
    source = repo / "docs/proposals" / PRP_NAME
    replace(
        source,
        "status: ready\ndepends_on: []",
        (
            "status: released\ndepends_on: []\n"
            "released_in: 1.2.0"
        ),
    )
    init_git(repo)
    assert_ok(
        mdf(
            python_exe,
            "archive",
            "--repo",
            str(repo),
            "--epoch",
            "1.2",
        )
    )

    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


@pytest.mark.parametrize("resolution", ["rejected", "obsolete", "duplicate"])
def test_proposal_rejects_unreleased_dependency(
    python_exe: str, tmp_path: Path, resolution: str
):
    repo = copy_fixture(tmp_path)
    write_proposal(repo, DEPENDENCY_ID, "health-client", f"[{PRP_ID}]")
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "status: ready\ndepends_on: []",
        f"status: rejected\ndepends_on: []\nreject-reason: {resolution}",
    )
    init_git(repo)

    assert "proposal.depends_on_unreleased" in validation_codes(
        python_exe, repo
    )


def test_proposal_rejects_duplicate_dependencies(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    write_proposal(
        repo,
        DEPENDENCY_ID,
        "health-client",
        f"[{PRP_ID}, {PRP_ID}]",
    )
    init_git(repo)

    assert "object.depends_on_duplicate" in validation_codes(
        python_exe, repo
    )


def test_proposal_rejects_self_dependency(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "depends_on: []",
        f"depends_on: [{PRP_ID}]",
    )
    init_git(repo)

    assert "proposal.depends_on_self" in validation_codes(python_exe, repo)


def test_proposal_rejects_dependency_cycle(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    write_proposal(repo, DEPENDENCY_ID, "health-client", f"[{PRP_ID}]")
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "depends_on: []",
        f"depends_on: [{DEPENDENCY_ID}]",
    )
    init_git(repo)

    assert "proposal.depends_on_cycle" in validation_codes(python_exe, repo)


def test_proposal_accepts_existing_milestone_dependency(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    write_proposal(repo, DEPENDENCY_ID, "health-client", '["阶段一"]')
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "depends_on: []",
        'depends_on: []\nmilestone: "阶段一"',
    )
    init_git(repo)

    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


def test_proposal_rejects_unknown_milestone_dependency(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "depends_on: []",
        'depends_on: ["不存在的阶段"]',
    )
    init_git(repo)

    assert "object.depends_on_missing" in validation_codes(python_exe, repo)


def test_proposal_rejects_own_milestone_dependency(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "depends_on: []",
        'depends_on: ["阶段一"]\nmilestone: "阶段一"',
    )
    init_git(repo)

    assert "proposal.depends_on_cycle" in validation_codes(python_exe, repo)


def test_proposal_rejects_cycle_through_milestone(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    write_proposal(repo, DEPENDENCY_ID, "health-client", '["阶段一"]')
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "depends_on: []",
        f'depends_on: [{DEPENDENCY_ID}]\nmilestone: "阶段一"',
    )
    init_git(repo)

    assert "proposal.depends_on_cycle" in validation_codes(python_exe, repo)
