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


def test_verification_commands_are_required_while_initializing(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    replace(
        repo / ".mdf" / "manifest.yaml",
        '  commands:\n    - id: check\n      kind: custom\n      command: "true"',
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
    assert "--verification-item" in result.stderr

    empty = mdf(
        python_exe,
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "none",
        *all_not_applicable_baselines(),
        "--verification-item",
        '{"id": "check", "kind": "custom", "command": "  "}',
    )
    assert empty.returncode != 0
    assert "invalid_verification" in empty.stderr


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


def test_mdf_clarify_delegates_or_clarifies_until_shared_understanding():
    skill = skill_dir("mdf")
    clarify = (skill / "references" / "clarify.md").read_text(encoding="utf-8")
    create = (skill / "references" / "prp-create.md").read_text(
        encoding="utf-8"
    )
    review = (skill / "references" / "prp-review.md").read_text(
        encoding="utf-8"
    )
    migrate = (skill / "references" / "migrate.md").read_text(encoding="utf-8")
    start = (skill / "references" / "start.md").read_text(encoding="utf-8")
    assert "系统 `grilling` skill" in clarify
    assert "委托它对议题执行压力测试" in clarify
    assert "报告该失败并停止" in clarify
    assert "不可用时进入 3" in clarify
    assert "等待回答后更新已确认决定与剩余疑问" in clarify
    assert "不得把未回答视为同意" in clarify
    assert "无未决疑问及用户明确确认" in clarify
    assert "用户取消、暂停或关键事实无法获得时列出未决项并停止" in "".join(
        clarify.split()
    )
    assert "内部 clarify intent" in create
    assert "内部 clarify intent" in review and "内部 clarify intent" in migrate
    assert "内部 clarify intent" in start
    assert "明确确认才转" in review


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


def test_merge_no_ff_commits_or_keeps_conflict(python_exe: str, tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--initial-branch=master", "--template=")
    git(repo, "commit", "--allow-empty", "-m", "base")
    git(repo, "checkout", "-b", "topic")
    (repo / "a.txt").write_text("topic\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-m", "topic")
    git(repo, "checkout", "master")
    merged = payload(
        mdf(python_exe, "merge-no-ff", "--repo", str(repo), "--commit", "topic")
    )
    assert merged["merged"] is True
    assert merged["branch"] == "master"

    again = payload(
        mdf(python_exe, "merge-no-ff", "--repo", str(repo), "--commit", "topic")
    )
    assert again["merged"] is False

    git(repo, "checkout", "-b", "left")
    (repo / "a.txt").write_text("left\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-m", "left")
    git(repo, "checkout", "master")
    git(repo, "checkout", "-b", "right")
    (repo / "a.txt").write_text("right\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-m", "right")
    conflict = mdf(
        python_exe, "merge-no-ff", "--repo", str(repo), "--commit", "left"
    )
    assert conflict.returncode != 0
    assert "merge_conflict" in conflict.stderr
    assert (repo / ".git" / "MERGE_HEAD").is_file()

