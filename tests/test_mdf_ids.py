"""MDF 对象 ID 与文件名测试。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403

_ID_LETTERS = set("ABCDEFGHJKLMNPQRSTUVWXYZ")
_ID_DIGITS = set("23456789")


def develop_repo(tmp_path: Path) -> Path:
    repo = copy_fixture(tmp_path)
    init_git(repo)
    checkout_develop(repo)
    return repo


def test_make_id_requires_an_ascii_slug(
    python_exe: str,
):
    result = mdf(python_exe, "make-id", "--type", "proposal")

    assert result.returncode != 0
    assert "--slug" in result.stderr


def test_make_id_proposal_requires_repo(python_exe: str):
    result = mdf(
        python_exe, "make-id", "--type", "proposal", "--slug", "service-health"
    )
    assert result.returncode != 0
    assert "missing_argument" in result.stderr


def test_make_id_proposal_requires_planning(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = mdf(
        python_exe,
        "make-id",
        "--type",
        "proposal",
        "--repo",
        str(repo),
        "--slug",
        "service-health",
    )
    assert result.returncode != 0
    assert "proposal_not_on_planning" in result.stderr
    checkout_develop(repo)
    result = mdf(
        python_exe,
        "make-id",
        "--type",
        "proposal",
        "--repo",
        str(repo),
        "--slug",
        "service-health",
    )
    assert "proposal_not_on_planning" in result.stderr


def test_make_id_rejects_object_id_slug(python_exe: str):
    result = mdf(
        python_exe, "make-id", "--type", "proposal", "--slug", "prp-001"
    )
    assert result.returncode != 0
    assert "slug_is_id" in result.stderr
    result = mdf(
        python_exe, "make-id", "--type", "proposal", "--slug", "adr-use-sqlite"
    )
    assert result.returncode != 0
    assert "slug_is_id" in result.stderr


def test_new_short_id_includes_a_letter_and_a_digit():
    load_core_module()
    from mdf_core.constants import OBJECT_ID_RE
    from mdf_core.textutil import new_short_id

    for _ in range(200):
        value = new_short_id()
        chars = set(value)
        assert chars <= _ID_LETTERS | _ID_DIGITS
        assert chars & _ID_LETTERS
        assert chars & _ID_DIGITS
        assert OBJECT_ID_RE.fullmatch(f"bug-{value}")


def test_format_prp_id_uses_three_digits_until_1000():
    load_core_module()
    from mdf_core.constants import PRP_ID_RE
    from mdf_core.textutil import format_prp_id

    assert format_prp_id(1) == "prp-001"
    assert format_prp_id(99) == "prp-099"
    assert format_prp_id(100) == "prp-100"
    assert format_prp_id(999) == "prp-999"
    assert format_prp_id(1000) == "prp-1000"
    assert format_prp_id(1001) == "prp-1001"
    for value in ("prp-001", "prp-099", "prp-100", "prp-999", "prp-1000"):
        assert PRP_ID_RE.fullmatch(value)
    for value in (
        "prp-000",
        "prp-01",
        "prp-1",
        "prp-01000",
        "prp-AB23",
        "prp-ABCD",
    ):
        assert PRP_ID_RE.fullmatch(value) is None


def test_make_id_proposal_increments_from_existing(
    python_exe: str, tmp_path: Path
):
    repo = develop_repo(tmp_path)
    work = planning_worktree(python_exe, repo)
    data = payload(
        mdf(
            python_exe,
            "make-id",
            "--type",
            "proposal",
            "--repo",
            str(work),
            "--slug",
            "mixed-id",
        )
    )
    assert data["id"] == "prp-002"
    assert data["filename"] == "prp-002-mixed-id.md"


def test_make_id_proposal_starts_at_001_when_empty(
    python_exe: str, tmp_path: Path
):
    repo = develop_repo(tmp_path)
    work = planning_worktree(python_exe, repo)
    (work / "docs/proposals" / PRP_NAME).unlink()
    data = payload(
        mdf(
            python_exe,
            "make-id",
            "--type",
            "proposal",
            "--repo",
            str(work),
            "--slug",
            "first-item",
        )
    )
    assert data["id"] == "prp-001"
    assert data["filename"] == "prp-001-first-item.md"


def test_make_id_proposal_drops_padding_after_999(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    template = (repo / "docs/proposals" / PRP_NAME).read_text()
    (repo / "docs/proposals" / "prp-999-ceiling.md").write_text(
        template.replace("prp-001", "prp-999")
    )
    init_git(repo)
    checkout_develop(repo)
    work = planning_worktree(python_exe, repo)
    data = payload(
        mdf(
            python_exe,
            "make-id",
            "--type",
            "proposal",
            "--repo",
            str(work),
            "--slug",
            "overflow",
        )
    )
    assert data["id"] == "prp-1000"
    assert data["filename"] == "prp-1000-overflow.md"


def test_make_id_bug_output_includes_a_letter_and_a_digit(python_exe: str):
    data = payload(
        mdf(python_exe, "make-id", "--type", "bug", "--slug", "mixed-id")
    )
    suffix = data["id"].split("-", 1)[1]
    chars = set(suffix)
    assert BUG_ID_RE.fullmatch(data["id"])
    assert chars & _ID_LETTERS
    assert chars & _ID_DIGITS


def test_id_validation_accepts_numeric_prp_and_homogeneous_bug_suffixes(
    python_exe: str, tmp_path: Path
):
    load_core_module()
    from mdf_core.constants import JOT_ID_RE, OBJECT_ID_RE, PRP_ID_RE

    assert OBJECT_ID_RE.fullmatch("prp-001")
    assert OBJECT_ID_RE.fullmatch("prp-1000")
    assert OBJECT_ID_RE.fullmatch("bug-2345")
    assert OBJECT_ID_RE.fullmatch("adr-use-sqlite")
    assert OBJECT_ID_RE.fullmatch("adr-0001") is None
    assert JOT_ID_RE.fullmatch("jot-AAAA")
    assert JOT_ID_RE.fullmatch("jot-2222")
    assert PRP_ID_RE.fullmatch("prp-ABCD") is None
    assert OBJECT_ID_RE.fullmatch("prp-ABCD") is None

    repo = copy_fixture(tmp_path)
    proposal = (repo / "docs/proposals" / PRP_NAME).read_text()
    (repo / "docs/proposals" / "prp-010-letters.md").write_text(
        proposal.replace("prp-001", "prp-010")
    )
    bug = (repo / "docs/bugs" / BUG_NAME).read_text()
    (repo / "docs/bugs" / "bug-2345-digits.md").write_text(
        bug.replace("bug-CD34", "bug-2345")
    )
    init_git(repo)
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


def write_adr(repo: Path, name: str, identifier: str) -> None:
    path = repo / "docs" / "context" / "adr" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {identifier}\ntype: adr\nstatus: accepted\n---\n\n# ADR\n",
        encoding="utf-8",
    )


def adr_codes(python_exe: str, repo: Path) -> set[str]:
    result = mdf(python_exe, "validate", "--repo", str(repo))
    assert result.returncode != 0
    return {item["code"] for item in json.loads(result.stdout)["findings"]}


def test_adr_id_equals_filename_slug(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    write_adr(repo, "use-sqlite.md", "adr-use-sqlite")
    init_git(repo)
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


def test_adr_rejects_legacy_numeric_id(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    write_adr(repo, "0001-use-sqlite.md", "adr-0001")
    init_git(repo)
    codes = adr_codes(python_exe, repo)
    assert "adr.id" in codes


def test_adr_rejects_id_not_matching_slug(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    write_adr(repo, "use-sqlite.md", "adr-0001")
    init_git(repo)
    assert "adr.id" in adr_codes(python_exe, repo)


def test_adr_rejects_digit_only_slug(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    write_adr(repo, "0001.md", "adr-0001")
    init_git(repo)
    assert "adr.filename" in adr_codes(python_exe, repo)


def test_adr_rejects_object_id_filename(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    write_adr(repo, "adr-use-sqlite.md", "adr-adr-use-sqlite")
    init_git(repo)
    assert "adr.slug_id" in adr_codes(python_exe, repo)
