"""仓内副本替换与项目缓存之间的升级交接。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from launcher_support import assert_pointer, copy_skill, invoke, payload, upstream
from mdf_test_support import git, init_git


def committed_copy(repo: Path, relative: str, revision: str) -> Path:
    tree = repo / relative
    copy_skill(tree)
    (tree / "references/.version").write_text(revision + "\n", encoding="utf-8")
    return tree


def test_completed_upgrade_installs_entry_and_preserves_project_changes(tmp_path: Path) -> None:
    source = upstream(tmp_path)
    revision = git(source, "rev-parse", "HEAD").stdout.strip()
    repo = tmp_path / "project"
    copied = committed_copy(repo, ".agents/skills/mdf", revision)
    second = committed_copy(repo, ".cursor/skills/mdf", revision)
    (repo / "docs").mkdir()
    (repo / "docs/fact.md").write_text("事实\n", encoding="utf-8")
    (repo / ".mdf").mkdir()
    (repo / ".mdf/manifest.yaml").write_text("schema_version: 3\n", encoding="utf-8")
    init_git(repo)
    (repo / "README.md").write_text("业务改动\n", encoding="utf-8")
    git(repo, "add", "README.md")

    home = tmp_path / "unused-home"
    upgraded = payload(invoke(home, [
        sys.executable, "-B", str(copied / "scripts/mdf_launcher.py"), "complete-upgrade",
        "--repo", str(repo), "--payload", str(copied), "--revision", revision, "--source", str(source),
    ], cwd=repo))
    assert upgraded["operation"] == "complete-upgrade"
    assert set(upgraded["detached"]) == {".agents/skills/mdf", ".cursor/skills/mdf"}
    assert not second.exists()
    assert_pointer(repo, revision, str(source))
    started = invoke(home, [sys.executable, "-B", upgraded["entry"]], cwd=repo)
    assert started.returncode == 0, started.stderr
    assert started.stdout.strip() == upgraded["root"]
    assert git(repo, "ls-files", "--", ".agents/skills/mdf", ".cursor/skills/mdf").stdout == ""
    assert "A\tREADME.md" in git(repo, "diff", "--cached", "--name-status").stdout
    assert (repo / "docs/fact.md").read_text(encoding="utf-8") == "事实\n"
    assert (repo / ".mdf/manifest.yaml").read_text(encoding="utf-8") == "schema_version: 3\n"
    assert not home.exists()

    git(source, "commit", "--allow-empty", "-m", "test: 发布下一版")
    next_revision = git(source, "rev-parse", "HEAD").stdout.strip()
    upgrade = [
        sys.executable, "-B", str(Path(upgraded["root"]) / "scripts/mdf_launcher.py"), "upgrade",
        "--repo", str(repo), "--source", str(source),
    ]
    preview = payload(invoke(home, [*upgrade, "--dry-run"], cwd=repo))
    assert preview["new_commit"] == next_revision
    replaced = payload(invoke(home, [*upgrade, "--expected-commit", next_revision], cwd=repo))
    assert_pointer(repo, next_revision, str(source))
    assert invoke(home, [sys.executable, "-B", upgraded["entry"]], cwd=repo).stdout.strip() == replaced["root"]
    assert not Path(upgraded["root"]).exists()


def test_failed_publish_restores_copy_index_and_ignore(tmp_path: Path, monkeypatch) -> None:
    import mdf_home
    from mdf_install_handoff import handoff

    revision = "a" * 40
    repo = tmp_path / "project"
    copied = committed_copy(repo, ".agents/skills/mdf", revision)
    ignore = repo / ".gitignore"
    ignore.write_text("/keep/\n", encoding="utf-8")
    init_git(repo)
    before = git(repo, "ls-files", "--", ".agents/skills/mdf").stdout

    def fail_entry(*_args):
        raise mdf_home.HomeError("模拟发布失败", "host_update_failed")

    monkeypatch.setattr(mdf_home, "install_entry", fail_entry)
    with pytest.raises(mdf_home.HomeError, match="模拟发布失败"):
        handoff(str(repo), copied, revision, "https://example.test/mdf")

    assert (copied / "scripts/mdf_launcher.py").is_file()
    assert git(repo, "ls-files", "--", ".agents/skills/mdf").stdout == before
    assert ignore.read_text(encoding="utf-8") == "/keep/\n"
    assert git(repo, "diff", "--cached", "--name-status").stdout == ""
