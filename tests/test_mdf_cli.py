"""MDF CLI 与 doctor 协议测试。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403


def test_info_reports_protocol_versions(python_exe: str):
    result = run(
        [python_exe, str(skill_dir("mdf") / "scripts" / "mdf.py"), "info"]
    )
    data = payload(result)
    assert data["ok"] is True
    assert data["tool"] == "mdf"
    assert data["protocol_version"] == 2
    assert data["tool_version"] == 2
    assert data["schema_version"] == 2


def test_doctor_reports_only_core_and_repository_state(
    python_exe: str, tmp_path: Path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["initialized"] is False
    assert data["findings"] == []
    assert data["normal_workflows_allowed"] is False
    assert "entry_skills" not in data


def test_doctor_reports_ready_v2_repository(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    init_git(repo)

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["initialized"] is True
    assert data["state"] == "ready"
    assert data["normal_workflows_allowed"] is True
    assert data["clean"] is True
    assert "entry_skills" not in data


def test_doctor_disallows_dirty_worktree(python_exe: str, tmp_path: Path):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    data = payload(mdf(python_exe, "doctor", "--repo", str(repo)))
    assert data["clean"] is False
    assert data["normal_workflows_allowed"] is False


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
        "schema_version: 2",
        "schema_version: 3",
    )
    init_git(repo)

    result = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert result.returncode != 0
    assert "manifest.schema" in result.stdout


def test_verification_commands_are_optional_only_while_initializing(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / ".mdf" / "manifest.yaml",
        '  commands:\n    - "true"',
        "  commands: []",
    )
    replace(
        repo / ".mdf" / "manifest.yaml", "state: ready", "state: initializing"
    )
    init_git(repo)

    targeted = mdf(python_exe, "validate", "--repo", str(repo))
    assert targeted.returncode != 0
    assert "manifest.initializing" in targeted.stdout
    assert "manifest.verification" not in targeted.stdout

    full = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert full.returncode != 0
    assert "manifest.verification" in full.stdout

    replace(
        repo / ".mdf" / "manifest.yaml", "state: initializing", "state: ready"
    )
    ready = mdf(python_exe, "validate", "--repo", str(repo))
    assert ready.returncode != 0
    assert "manifest.verification" in ready.stdout


def test_removed_verify_command_argument_is_a_hard_failure(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    result = mdf(
        python_exe,
        "release-closeout",
        "--repo",
        str(repo),
        "--verify-command",
        "true",
    )
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr


def test_mdf_grill_is_internal_workflow_copy():
    skill = skill_dir("mdf")
    grill = (skill / "workflows" / "grill.md").read_text(encoding="utf-8")
    review = (skill / "workflows" / "review-doc.md").read_text(encoding="utf-8")
    init = (skill / "workflows" / "init-repo.md").read_text(encoding="utf-8")

    assert "持续、深入地追问" in grill
    assert "一次只问一个问题" in grill
    assert "查证的事实自行查证" in grill
    assert "不要据此采取行动" in grill
    assert "内部 grill 工作流" in review and "内部 grill 工作流" in init
    assert "明确确认才转" in review
