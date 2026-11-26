"""ADR 的 ID 与文件名校验。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def write_adr(repo: Path, name: str, identifier: str) -> None:
    path = repo / "docs" / "context" / "adr" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {identifier}\ntype: adr\nstatus: accepted\n---\n\n# ADR\n",
        encoding="utf-8",
    )


def adr_codes(python_exe: str, repo: Path) -> set[str]:
    result = mdf(python_exe, "validate", "--repo", str(repo), "--level", "strict")
    assert result.returncode != 0
    return {item["code"] for item in json.loads(result.stdout)["findings"]}


def test_adr_id_equals_filename_slug(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    write_adr(repo, "use-sqlite.md", "adr-use-sqlite")
    init_git(repo)
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo), "--level", "strict"))


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
