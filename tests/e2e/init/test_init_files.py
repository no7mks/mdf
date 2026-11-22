"""init 写入的文件、既有内容保留与续办。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_init_allows_dirty_worktree_for_active_continuation(
    python_exe: str, tmp_path: Path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Test\n", encoding="utf-8")
    init_git(repo)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    arguments = [
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "none",
        *all_not_applicable_baselines(),
        *verification_args(),
    ]

    applied = payload(mdf(python_exe, *arguments))
    assert applied["operation"] == "init"
    assert (repo / ".mdf" / "manifest.yaml").is_file()
    assert (repo / "docs/JOTS.md").read_text(encoding="utf-8") == "# 随手记录\n"


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
        *verification_args(),
        "--budget",
        "quick=45",
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
    assert 'logo: "📍"' in manifest
    assert "latest_release: null" in manifest
    assert "verification:" not in manifest
    modules = (repo / ".mdf" / "modules.yaml").read_text(encoding="utf-8")
    assert 'lint: "true"' in modules or "lint:" in modules
    assert "budgets:" in modules
    assert "quick: 45" in modules
    full = mdf(
        python_exe,
        "validate",
        "--repo",
        str(repo),
        "--level",
        "strict",
    )
    assert full.returncode != 0
    assert "manifest.initializing" in full.stdout
    assert "modules.invalid" not in full.stdout
    assert "manifest.verification_moved" not in full.stdout

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
        *verification_args(),
    ]
    applied = payload(mdf(python_exe, *arguments))
    assert ".gitignore" in applied["plan"]["create"]
    assert (repo / ".gitignore").read_text(encoding="utf-8") == (
        "# MDF local artifacts\n"
        "/.mdf/logs/\n"
        "/.mdf/tmp/\n"
        "/.mdf/reports/\n"
        "/.mdf/cache/\n"
    )

    templates = skill_dir("mdf") / "assets" / "templates"
    docs_index = (repo / "docs" / "README.md").read_text(encoding="utf-8")
    template_index = (templates / "docs-readme.md").read_text(encoding="utf-8")
    # all_not_applicable baselines 移除 user-guide、system boundary 与 deviations 链接行
    removed = ("](user-guide/README.md)", "](system/overview.md)", "](system/deviations.md)")
    expected_index = "".join(
        line for line in template_index.splitlines(keepends=True)
        if not any(marker in line for marker in removed)
    )
    assert docs_index == expected_index
    assert docs_index != "# 文档\n"
    assert "user-guide" not in docs_index.split("## 决策")[0].split("## 当前事实")[1]
    assert (repo / "docs/context/research/.gitkeep").is_file()
    assert (repo / "docs/context/adr/.gitkeep").is_file()
    assert (repo / "docs/user-guide/.gitkeep").is_file()
    assert not (repo / "docs/product").exists()
    assert not (repo / "docs/adr").exists()
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
    assert "单 module 为 `src/` 与 `tests/`" in project
    assert "`<module>/src/`" in project
    assert "`<module>/tests/`" in project
    assert "允许处于仓库顶层的例外" in project

    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    block = (
        (templates / "agents-managed-block.md")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert agents == "# AGENTS.md\n\n" + block + "\n"
    for name in ("proposals", "bugs", "context/research"):
        assert (repo / "docs" / name / ".gitkeep").is_file()
    assert (repo / "changes/unreleased/.gitkeep").is_file()
    assert not (repo / "docs/specs").exists()
    assert (repo / "docs/JOTS.md").is_file()
    assert (repo / "docs/system/testing/index.md").is_file()
    assert (repo / "docs/system/testing/conventions.md").is_file()
    assert (repo / "docs/system/testing/index.md").read_text(
        encoding="utf-8"
    ) == (templates / "system-testing-index.md").read_text(encoding="utf-8")
    assert (repo / "docs/system/testing/conventions.md").read_text(
        encoding="utf-8"
    ) == (templates / "system-testing-conventions.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("logo, expected", [
    (None, "📍"), ("null", "📍"), ('""', "📍"), ('"📍"', "📍"), ('"🚀"', "🚀"),
])
def test_init_updates_existing_manifest_and_managed_block(
    python_exe: str, tmp_path: Path, logo: str | None, expected: str
):
    repo = copy_fixture(tmp_path)
    init_git(repo)
    manifest_path = repo / ".mdf" / "manifest.yaml"
    if logo is not None:
        with manifest_path.open("a", encoding="utf-8") as stream:
            stream.write(f"logo: {logo}\n")
    arguments = [
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "1.2.0",
        *fixture_documented_baselines(),
        *verification_args(),
    ]

    payload(mdf(python_exe, *arguments))

    manifest = (repo / ".mdf" / "manifest.yaml").read_text(encoding="utf-8")
    assert "schema_version: 3" in manifest
    assert f'logo: "{expected}"' in manifest
    assert 'latest_release: "1.2.0"' in manifest
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count("<!-- MDF:BEGIN -->") == 1
    assert 'path: "docs/user-guide/README.md"' in manifest
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
        *verification_args(),
    ]
    applied = payload(mdf(python_exe, *arguments))
    assert "dry_run" not in applied
    assert "plan_digest" not in applied
    assert (repo / ".mdf" / "manifest.yaml").is_file()

    rejected = mdf(
        python_exe, *arguments, "--plan-digest", "sha256:" + "0" * 64
    )
    assert rejected.returncode != 0


def test_init_gitignore_is_idempotent_and_keeps_user_rules(
    python_exe: str, tmp_path: Path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Test repository\n", encoding="utf-8")
    (repo / ".gitignore").write_text("node_modules/\n/.mdf/tmp/\n/.agents/skills/mdf/\n", encoding="utf-8")
    init_git(repo)
    arguments = [
        "init",
        "--repo",
        str(repo),
        "--latest-release",
        "none",
        *all_not_applicable_baselines(),
        *verification_args(),
    ]
    first = payload(mdf(python_exe, *arguments))
    assert ".gitignore" in first["plan"]["update"]
    text = (repo / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith("node_modules/\n/.mdf/tmp/\n\n# MDF local artifacts\n")
    assert text.count("/.mdf/tmp/") == 1
    for line in ("/.mdf/logs/", "/.mdf/reports/", "/.mdf/cache/"):
        assert text.count(line) == 1
    assert "/.agents/skills/mdf/" not in text
    second = payload(mdf(python_exe, *arguments))
    assert ".gitignore" not in second["plan"]["create"]
    assert ".gitignore" not in second["plan"]["update"]
    assert (repo / ".gitignore").read_text(encoding="utf-8") == text
    tracked = run(["git", "check-ignore", "-q", ".mdf/manifest.yaml"], cwd=repo)
    assert tracked.returncode == 1
    ignored = run(
        ["git", "check-ignore", "-q", ".mdf/cache/mdf-core/" + "a" * 40], cwd=repo,
    )
    assert ignored.returncode == 0
