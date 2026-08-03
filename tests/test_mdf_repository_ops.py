"""Mars Development Flow 的确定性协议与事务测试。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403


def test_archive_dry_run_then_moves_closed_item_and_rewrites_links(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    requirement = repo / "requirements" / REQ_NAME
    replace(
        requirement,
        "status: ready\nrelated: []",
        (
            "status: closed\nrelated: []\n"
            "resolution: fulfilled\n"
            "fulfilled_in: 1.2.0"
        ),
    )
    requirement.write_text(
        requirement.read_text(encoding="utf-8")
        + f'\n[Known bug](../bugs/{BUG_NAME}#impact "Regression context")\n',
        encoding="utf-8",
    )
    init_git(repo)

    dry_run = mdf(
        python_exe,
        "archive",
        "--repo",
        str(repo),
        "--epoch",
        "1.2",
        "--dry-run",
    )
    assert_ok(dry_run)
    assert REQ_NAME in dry_run.stdout
    assert "plan_digest" not in json.loads(dry_run.stdout)
    assert requirement.is_file(), "dry-run 不得移动文件"
    assert not (repo / "requirements" / "archive" / "1.2" / REQ_NAME).exists()
    assert not git(repo, "status", "--porcelain").stdout

    applied = mdf(
        python_exe,
        "archive",
        "--repo",
        str(repo),
        "--epoch",
        "1.2",
    )
    assert_ok(applied)
    archived = repo / "requirements" / "archive" / "1.2" / REQ_NAME
    assert archived.is_file()
    assert not requirement.exists()
    archived_text = archived.read_text(encoding="utf-8")
    assert (
        f'../../../bugs/{BUG_NAME}#impact "Regression context"' in archived_text
    )

    reference = (
        repo / "docs" / "product" / "reference" / "capabilities.md"
    ).read_text(encoding="utf-8")
    assert f"../../../requirements/archive/1.2/{REQ_NAME}" in reference
    assert f"../../../requirements/{REQ_NAME}" not in reference


def test_archive_never_rewrites_external_url_path_text(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    requirement = repo / "requirements" / REQ_NAME
    replace(
        requirement,
        "status: ready\nrelated: []",
        "status: closed\nrelated: []\nresolution: rejected",
    )
    external_url = f"https://example.invalid/repository/requirements/{REQ_NAME}"
    index = repo / "docs" / "index.md"
    index.write_text(
        index.read_text(encoding="utf-8")
        + f"\n[External requirement]({external_url})\n",
        encoding="utf-8",
    )
    init_git(repo)
    arguments = [
        "archive",
        "--repo",
        str(repo),
        "--epoch",
        "1.2",
    ]

    plan = payload(mdf(python_exe, *arguments, "--dry-run"))
    assert "docs/index.md" not in plan["rewrites"]
    payload(mdf(python_exe, *arguments))
    assert external_url in index.read_text(encoding="utf-8")


def test_init_dry_run_then_apply_preserves_existing_agents_content(
    python_exe: str, tmp_path: Path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Existing project\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text(
        "# Existing rules\n\n- Keep this exact rule.\n",
        encoding="utf-8",
    )
    init_git(repo)
    arguments = [
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "none",
        *all_not_applicable_baselines(),
    ]
    sentinel_arguments = [
        "0.0.0-unreleased" if value == "none" else value for value in arguments
    ]
    sentinel_result = mdf(python_exe, *sentinel_arguments, "--dry-run")
    assert sentinel_result.returncode != 0

    dry_run = payload(mdf(python_exe, *arguments, "--dry-run"))
    assert dry_run["plan"]["mode"] == "initialization"
    assert ".mdf/manifest.yaml" in dry_run["plan"]["create"]
    assert "plan_digest" not in dry_run
    assert "repository_state" not in dry_run["plan"]
    assert not (repo / ".mdf").exists()

    payload(mdf(python_exe, *arguments))
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "Keep this exact rule." in agents
    assert agents.count("<!-- MDF:BEGIN -->") == 1
    assert agents.count("<!-- MDF:END -->") == 1
    manifest = (repo / ".mdf" / "manifest.yaml").read_text(encoding="utf-8")
    assert "state: initializing" in manifest
    assert "latest_release: null" in manifest

    replace(
        repo / ".mdf" / "manifest.yaml", "state: initializing", "state: ready"
    )
    replace(
        repo / ".mdf" / "manifest.yaml",
        "  commands: []",
        '  commands:\n    - "true"',
    )
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


def test_init_writes_files_from_assets_templates(
    python_exe: str, tmp_path: Path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Test repository\n", encoding="utf-8")
    init_git(repo)
    arguments = [
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "none",
        *all_not_applicable_baselines(),
    ]
    dry_run = payload(mdf(python_exe, *arguments, "--dry-run"))
    payload(mdf(python_exe, *arguments))

    templates = skill_dir("mdf") / "assets" / "templates"
    docs_index = (repo / "docs" / "index.md").read_text(encoding="utf-8")
    expected_index = (templates / "docs-index.md").read_text(encoding="utf-8")
    # all_not_applicable baselines 移除 system boundary 与 deviations 两行
    expected_index = expected_index.replace(
        "- [System boundary](system/overview.md)\n", ""
    )
    expected_index = expected_index.replace(
        "- [Known deviations](system/deviations.md)\n", ""
    )
    assert docs_index == expected_index
    assert docs_index != "# Documentation\n"
    assert (repo / "docs" / "research" / ".gitkeep").is_file()
    assert "[Research notes](research/)" in docs_index

    changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog == (templates / "changelog.md").read_text(encoding="utf-8")
    assert changelog != "# Changelog\n\nReleased versions are recorded here.\n"

    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    block = (
        (templates / "agents-managed-block.md")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert block in agents


def test_init_updates_existing_manifest_and_managed_block(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    arguments = [
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "1.2.0",
        *fixture_documented_baselines(),
    ]

    dry_run = payload(mdf(python_exe, *arguments, "--dry-run"))
    plan = dry_run["plan"]
    assert plan["mode"] == "update"
    assert ".mdf/manifest.yaml" in plan["update"]
    payload(mdf(python_exe, *arguments))

    manifest = (repo / ".mdf" / "manifest.yaml").read_text(encoding="utf-8")
    assert "schema_version: 2" in manifest
    assert 'latest_release: "1.2.0"' in manifest
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count("<!-- MDF:BEGIN -->") == 1
    assert 'path: "docs/product/reference/capabilities.md"' in manifest
    assert 'path: "docs/system/architecture/current.md"' in manifest


def test_init_executes_directly_without_plan_digest(
    python_exe: str, tmp_path: Path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Test repository\n", encoding="utf-8")
    init_git(repo)
    arguments = [
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "none",
        *all_not_applicable_baselines(),
    ]
    applied = payload(mdf(python_exe, *arguments))
    assert applied["dry_run"] is False
    assert "plan_digest" not in applied
    assert (repo / ".mdf" / "manifest.yaml").is_file()

    rejected = mdf(
        python_exe, *arguments, "--plan-digest", "sha256:" + "0" * 64
    )
    assert rejected.returncode != 0


def test_move_change_dry_run_preserves_source_then_moves_tree(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    source = repo / "working-notes" / "api-user-auth"
    source.mkdir(parents=True)
    artifact = source / "notes.md"
    artifact.write_text("# External planning artifact\n", encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 准备外部材料")
    arguments = [
        "move-change",
        "--repo",
        str(repo),
        "--source",
        str(source),
        "--branch-slug",
        "api/user_auth",
    ]

    dry_run = payload(mdf(python_exe, *arguments, "--dry-run"))
    assert dry_run["target"] == "changes/unreleased/api-user-auth"
    assert "plan_digest" not in dry_run
    assert artifact.is_file()

    payload(mdf(python_exe, *arguments))
    target = repo / "changes" / "unreleased" / "api-user-auth"
    assert (target / "notes.md").read_text(encoding="utf-8") == (
        "# External planning artifact\n"
    )
    assert not source.exists()


def test_move_change_rejects_source_with_mismatched_slug(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    source = repo / "working-notes" / "different-change"
    source.mkdir(parents=True)
    result = mdf(
        python_exe,
        "move-change",
        "--repo",
        str(repo),
        "--source",
        str(source),
        "--branch-slug",
        "api-user-auth",
        "--dry-run",
    )
    assert result.returncode != 0
    assert "source_slug" in result.stderr
    assert source.is_dir()


def test_move_change_never_overwrites_opaque_reserved_change(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    source = repo / "working-notes" / "api-user-auth"
    source.mkdir(parents=True)
    reserved = source / "CHANGE.md"
    reserved.write_text(
        "# External file with a reserved name\n", encoding="utf-8"
    )
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "test: 准备保留文件")

    result = mdf(
        python_exe,
        "move-change",
        "--repo",
        str(repo),
        "--source",
        str(source),
        "--branch-slug",
        "api-user-auth",
        "--dry-run",
    )
    assert result.returncode != 0
    assert "reserved_change" in result.stderr
    assert reserved.read_text(encoding="utf-8") == (
        "# External file with a reserved name\n"
    )
