"""make-id 的 Proposal 与 Bug 编号。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403
from types import SimpleNamespace
from support_delivery import *  # noqa: F403
from support_upgrade import *  # noqa: F403


_ID_LETTERS = set("ABCDEFGHJKLMNPQRSTUVWXYZ")


_ID_DIGITS = set("0123456789")


def develop_repo(tmp_path: Path) -> Path:
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "master")
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
        python_exe, "make-id", "--type", "proposal", "--slug", "prp-0001"
    )
    assert result.returncode != 0
    assert "slug_is_id" in result.stderr
    result = mdf(
        python_exe, "make-id", "--type", "proposal", "--slug", "adr-use-sqlite"
    )
    assert result.returncode != 0
    assert "slug_is_id" in result.stderr


def test_make_id_proposal_avoids_existing(
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
    assert PRP_ID_RE.fullmatch(data["id"])
    assert data["id"] != PRP_ID
    assert data["filename"] == f"{data['id']}-mixed-id.md"


def test_make_id_proposal_generates_when_empty(
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
    assert PRP_ID_RE.fullmatch(data["id"])
    assert data["filename"] == f"{data['id']}-first-item.md"


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
    from mdf_core.foundation.constants import JOT_ID_RE, OBJECT_ID_RE, PRP_ID_RE

    assert OBJECT_ID_RE.fullmatch("prp-0001")
    assert OBJECT_ID_RE.fullmatch("prp-1000")
    assert OBJECT_ID_RE.fullmatch("bug-0101")
    assert OBJECT_ID_RE.fullmatch("adr-use-sqlite")
    assert OBJECT_ID_RE.fullmatch("adr-0001") is None
    assert JOT_ID_RE.fullmatch("jot-AAAA")
    assert JOT_ID_RE.fullmatch("jot-0101")
    assert PRP_ID_RE.fullmatch("prp-ABCD") is None
    assert OBJECT_ID_RE.fullmatch("prp-ABCD") is None

    repo = copy_fixture(tmp_path)
    proposal = (repo / "docs/proposals" / PRP_NAME).read_text()
    (repo / "docs/proposals" / "prp-0010-letters.html").write_text(
        proposal.replace("prp-0001", "prp-0010")
    )
    bug = (repo / "docs/bugs" / BUG_NAME).read_text()
    (repo / "docs/bugs" / "bug-0101-digits.md").write_text(
        bug.replace("bug-CD34", "bug-0101")
    )
    init_git(repo)
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


def test_make_id_bug_uses_the_type_specific_format_and_normalized_slug(
    python_exe: str,
):
    data = payload(
        mdf(python_exe, "make-id", "--type", "bug", "--slug", "  Audit Ready 42!  ")
    )
    assert BUG_ID_RE.fullmatch(data["id"])
    assert data["id"].startswith("bug-")
    assert data["filename"] == f"{data['id']}-audit-ready-42.md"


def test_make_id_proposal_uses_random_id_and_normalized_slug(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "master")
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
            "  Audit Ready 42!  ",
        )
    )
    assert PRP_ID_RE.fullmatch(data["id"])
    assert data["id"] != PRP_ID
    assert data["filename"] == f"{data['id']}-audit-ready-42.md"


def test_new_id_alias_no_longer_exists(python_exe: str):
    cli = skill_dir("mdf") / "scripts" / "mdf.py"
    result = run(
        [python_exe, str(cli), "new-id", "--type", "bug", "--slug", "x"]
    )
    assert result.returncode != 0


def test_batch_prp_ids_do_not_write_or_repeat(python_exe, tmp_path):
    repo, _ = start_repo(tmp_path)
    git(repo, "checkout", "develop")
    work = planning_worktree(python_exe, repo)
    head = source_head(work)
    data = payload(mdf(python_exe, "make-id", "--type", "proposal", "--repo", str(work),
                       "--slug", "part-one", "--slug", "part-two"))
    identifiers = [item["id"] for item in data["items"]]
    assert len(set(identifiers)) == 2
    assert PRP_ID not in identifiers
    assert all(PRP_ID_RE.fullmatch(value) for value in identifiers)
    assert data["items"][1]["filename"] == f"{identifiers[1]}-part-two.md"
    assert source_head(work) == head
    assert not git(work, "status", "--porcelain").stdout
    body = proposal_markdown(work / "docs/proposals" / PRP_NAME).split("---", 2)[2]
    spec = {"source": "prp-0001", "children": [
        {"id": item["id"], "filename": item["filename"], "depends_on": [], "body": body}
        for item in data["items"]], "downstream": {}, "rationale": "用户确认分成两项"}
    path = tmp_path / "split.json"
    path.write_text(json.dumps(spec))
    args = ["prp-split", "--repo", str(work), "--spec-file", str(path)]
    preview = payload(mdf(python_exe, *args, "--dry-run"))
    applied = payload(mdf(python_exe, *args))
    assert preview["files"] == applied["files"]
