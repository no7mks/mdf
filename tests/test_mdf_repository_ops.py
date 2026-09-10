"""Mars Development Flow 的确定性协议与事务测试。"""

from __future__ import annotations

from mdf_test_support import *  # noqa: F403


def test_archive_dry_run_then_moves_closed_item_and_rewrites_links(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    proposal = repo / "docs/proposals" / PRP_NAME
    replace(
        proposal,
        "status: ready\ndepends_on: []",
        (
            "status: released\ndepends_on: []\n"
            ""
            "released_in: 1.2.0"
        ),
    )
    proposal.write_text(
        proposal.read_text(encoding="utf-8")
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
    assert PRP_NAME in dry_run.stdout
    assert "plan_digest" not in json.loads(dry_run.stdout)
    assert proposal.is_file(), "dry-run 不得移动文件"
    assert not (repo / "docs/proposals" / "archive" / "1.2" / PRP_NAME).exists()
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
    archived = repo / "docs/proposals" / "archive" / "1.2" / PRP_NAME
    assert archived.is_file()
    assert not proposal.exists()
    archived_text = archived.read_text(encoding="utf-8")
    assert (
        f'../../../bugs/{BUG_NAME}#impact "Regression context"' in archived_text
    )

    reference = (
        repo / "docs" / "product" / "reference" / "capabilities.md"
    ).read_text(encoding="utf-8")
    assert f"../../proposals/archive/1.2/{PRP_NAME}" in reference
    assert f"../../proposals/{PRP_NAME}" not in reference


def test_archive_never_rewrites_external_url_path_text(
    python_exe: str, tmp_path: Path
):
    repo = copy_fixture(tmp_path)
    proposal = repo / "docs/proposals" / PRP_NAME
    replace(
        proposal,
        "status: ready\ndepends_on: []",
        "status: rejected\ndepends_on: []\nreject-reason: wont-do",
    )
    external_url = f"https://example.invalid/repository/proposals/{PRP_NAME}"
    index = repo / "docs" / "README.md"
    index.write_text(
        index.read_text(encoding="utf-8")
        + f"\n[External proposal]({external_url})\n",
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
    assert "docs/README.md" not in plan["rewrites"]
    payload(mdf(python_exe, *arguments))
    assert external_url in index.read_text(encoding="utf-8")


def test_init_rejects_dry_run_then_preserves_existing_agents_content(
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
        "--verification-item",
        '{"id": "check", "kind": "custom", "command": "true"}',
    ]
    sentinel_arguments = [
        "0.0.0-unreleased" if value == "none" else value for value in arguments
    ]
    sentinel_result = mdf(python_exe, *sentinel_arguments)
    assert sentinel_result.returncode != 0

    preview = mdf(python_exe, *arguments, "--dry-run")
    assert preview.returncode != 0
    assert not (repo / ".mdf").exists()

    payload(mdf(python_exe, *arguments))
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "Keep this exact rule." in agents
    assert agents.count("<!-- MDF:BEGIN -->") == 1
    assert agents.count("<!-- MDF:END -->") == 1
    manifest = (repo / ".mdf" / "manifest.yaml").read_text(encoding="utf-8")
    assert "state: initializing" in manifest
    assert "latest_release: null" in manifest
    assert '      command: "true"' in manifest
    full = mdf(
        python_exe,
        "validate",
        "--repo",
        str(repo),
        "--scope",
        "full",
    )
    assert full.returncode != 0
    assert "manifest.initializing" in full.stdout
    assert "manifest.verification" not in full.stdout

    replace(
        repo / ".mdf" / "manifest.yaml", "state: initializing", "state: ready"
    )
    assert_ok(mdf(python_exe, "validate", "--repo", str(repo)))


def test_init_writes_files_from_assets_templates(
    python_exe: str, tmp_path: Path
):
    (tmp_path / "AGENTS.md").write_text("- Parent-only rule.\n")
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
        "--verification-item",
        '{"id": "check", "kind": "custom", "command": "true"}',
    ]
    payload(mdf(python_exe, *arguments))

    templates = skill_dir("mdf") / "assets" / "templates"
    docs_index = (repo / "docs" / "README.md").read_text(encoding="utf-8")
    expected_index = (templates / "docs-readme.md").read_text(encoding="utf-8")
    # all_not_applicable baselines 移除 system boundary 与 deviations 两行
    expected_index = expected_index.replace(
        "- [系统边界](system/overview.md)\n", ""
    )
    expected_index = expected_index.replace(
        "- [已知偏差](system/deviations.md)\n", ""
    )
    assert docs_index == expected_index
    assert docs_index != "# 文档\n"
    assert (repo / "docs/context/research/.gitkeep").is_file()
    assert not (repo / "docs/context" / "requirements").exists()
    assert not (repo / "docs/context" / "planning").exists()

    changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog == (templates / "changelog.md").read_text(encoding="utf-8")
    assert changelog != "# Changelog\n\n本文件记录已发布的版本。\n"

    glossary = (repo / "GLOSSARY.md").read_text(encoding="utf-8")
    assert glossary == (templates / "glossary.md").read_text(encoding="utf-8")

    project = (repo / "PROJECT.md").read_text(encoding="utf-8")
    assert project == (templates / "project.md").read_text(encoding="utf-8")
    assert "## 目录约定" in project
    assert "`src/` 中的业务实现" in project
    assert "允许处于仓库顶层的例外" in project

    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    block = (
        (templates / "agents-managed-block.md")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert agents == "# AGENTS.md\n\n" + block + "\n"
    for name in ("proposals", "bugs", "changes/unreleased", "specs", "context/research"):
        assert (repo / "docs" / name / ".gitkeep").is_file()
    assert (repo / "docs/JOTS.md").is_file()


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
        "--verification-item",
        '{"id": "check", "kind": "custom", "command": "true"}',
    ]

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
        "--verification-item",
        '{"id": "check", "kind": "custom", "command": "true"}',
    ]
    applied = payload(mdf(python_exe, *arguments))
    assert "dry_run" not in applied
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
    assert dry_run["target"] == "docs/changes/unreleased/api-user-auth"
    assert "plan_digest" not in dry_run
    assert artifact.is_file()

    payload(mdf(python_exe, *arguments))
    target = repo / "docs/changes" / "unreleased" / "api-user-auth"
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
