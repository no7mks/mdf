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


def test_verification_commands_are_required_while_initializing(
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
    assert "manifest.verification" in targeted.stdout

    full = mdf(python_exe, "validate", "--repo", str(repo), "--scope", "full")
    assert full.returncode != 0
    assert "manifest.verification" in full.stdout

    replace(
        repo / ".mdf" / "manifest.yaml", "state: initializing", "state: ready"
    )
    ready = mdf(python_exe, "validate", "--repo", str(repo))
    assert ready.returncode != 0
    assert "manifest.verification" in ready.stdout


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
    assert "--verification-command" in result.stderr

    empty = mdf(
        python_exe,
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "none",
        *all_not_applicable_baselines(),
        "--verification-command",
        "  ",
    )
    assert empty.returncode != 0
    assert "invalid_verification_command" in empty.stderr


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


def test_mdf_grill_is_internal_intent_copy():
    skill = skill_dir("mdf")
    grill = (skill / "intents" / "grill.md").read_text(encoding="utf-8")
    create = (skill / "intents" / "doc-create.md").read_text(
        encoding="utf-8"
    )
    review = (skill / "intents" / "doc-review.md").read_text(
        encoding="utf-8"
    )
    init = (skill / "intents" / "init.md").read_text(encoding="utf-8")

    assert "持续、深入地追问" in grill
    assert "展示简明的决策树" in grill
    assert "预计总题量" in grill
    assert "当前题号/总题量" in grill
    assert "一轮可包含多个\n问题" in grill
    assert "查证的事实自行查证" in grill
    assert "不要据此采取行动" in grill
    assert "内部 grill intent" in create
    assert "内部 grill intent" in review and "内部 grill intent" in init
    assert "明确确认才转" in review
