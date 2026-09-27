"""info、doctor 与 validate 报告的仓库状态。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_info_reports_protocol_versions(python_exe: str):
    result = run(
        [python_exe, str(skill_dir("mdf") / "scripts" / "mdf.py"), "info"]
    )
    data = payload(result)
    assert data["ok"] is True
    assert data["tool"] == "mdf"
    assert data["protocol_version"] == 3
    assert data["tool_version"] == 3
    assert data["schema_version"] == 3


def test_doctor_reports_only_core_and_repository_state(
    python_exe: str, tmp_path: Path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["initialized"] is False
    assert {item["code"] for item in data["findings"]} == {"layout.testing"}
    assert data["normal_workflows_allowed"] is False
    assert "entry_skills" not in data


def test_doctor_reports_retired_layout_without_manifest(python_exe: str, tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "docs/product").mkdir(parents=True)
    (repo / "docs/product/note.md").write_text("旧产品说明。\n", encoding="utf-8")

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["initialized"] is False
    codes = {item["code"] for item in data["findings"]}
    assert "layout.migrate" in codes
    assert data["is_git_root"] is False


def test_doctor_reports_ready_v2_repository(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["initialized"] is True
    assert data["state"] == "ready"
    assert data["normal_workflows_allowed"] is True
    assert data["clean"] is True
    assert "entry_skills" not in data


def test_doctor_reports_dirty_without_blocking_normal_workflows(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["clean"] is False
    assert data["normal_workflows_allowed"] is True
    assert data["findings"] == []
    assert (repo / "untracked.txt").read_text() == "dirty\n"


def test_doctor_allows_in_progress_unreleased_delivery_without_change(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    git(repo, "branch", "-m", "master")
    git(repo, "branch", "develop")
    obj = tmp_path / "objectives.md"
    obj.write_text("# 目标\n\n交付健康接口。\n")
    started = payload(
        mdf(
            python_exe,
            "start",
            "--repo",
            str(repo),
            "--kind",
            "feature",
            "--proposal",
            "prp-001",
            "--objectives-file",
            str(obj),
        )
    )
    work = Path(started["worktree"])
    root = work / "changes/unreleased/service-health"
    assert (root / "delivery.json").is_file()
    assert (root / "objectives.md").is_file()
    assert not (root / "CHANGE.md").exists()

    data = payload(mdf(python_exe, "doctor", "--repo", str(work)))
    assert data["state"] == "ready"
    assert data["findings"] == []
    assert data["normal_workflows_allowed"] is True
    assert data["clean"] is True


def test_doctor_rejects_unreleased_dir_without_change_or_identity(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    folder = repo / "changes/unreleased/orphan-slug"
    folder.mkdir(parents=True)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["normal_workflows_allowed"] is False
    codes = {item["code"] for item in data["findings"]}
    assert "change.missing" in codes


def test_doctor_allows_semver_unreleased_review_dir(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    folder = repo / "changes/unreleased/1.2.1"
    folder.mkdir(parents=True)
    (folder / "code-review.md").write_text("# 审查\n\n通过。\n", encoding="utf-8")
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["findings"] == []
    assert data["normal_workflows_allowed"] is True


def test_doctor_allows_semver_unreleased_identity_without_review(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    folder = repo / "changes/unreleased/1.3.0"
    folder.mkdir(parents=True)
    (folder / "delivery.json").write_text("{}\n", encoding="utf-8")
    (folder / "objectives.md").write_text("# 发布目标\n\n本版收口。\n")
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["findings"] == []
    assert data["normal_workflows_allowed"] is True


def test_doctor_rejects_empty_semver_unreleased_dir(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    folder = repo / "changes/unreleased/1.3.0"
    folder.mkdir(parents=True)
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["normal_workflows_allowed"] is False
    codes = {item["code"] for item in data["findings"]}
    assert "change.missing" in codes


def test_doctor_allows_ignored_runtime_files(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    (repo / ".gitignore").write_text(".lark/\n", encoding="utf-8")
    init_git(repo)
    token_dir = repo / ".lark"
    token_dir.mkdir()
    (token_dir / "token.json").write_text("{}\n", encoding="utf-8")

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["clean"] is True


def test_validate_rejects_noncurrent_manifest_schema(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / ".mdf" / "manifest.yaml",
        "schema_version: 3",
        "schema_version: 2",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert result.returncode != 0
    assert "manifest.schema" in result.stdout
