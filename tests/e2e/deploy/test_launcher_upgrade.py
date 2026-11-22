"""仓外升级：预览、回滚，以及旧 Core 损坏时仍能升级。"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest

from launcher_support import (
    REV_A,
    REV_B,
    SKILL,
    assert_host_copies,
    copy_skill,
    error,
    invoke,
    payload,
    root_of,
    upstream,
)
from mdf_test_support import git, init_git


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "--all")
    git(repo, "commit", "-m", message)


def test_upgrade_dry_run_then_rejects_moved_source(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    first = head(source)
    preview = payload(invoke(
        home, [sys.executable, "-B", str(source / "skills/mdf/scripts/mdf_launcher.py"),
               "upgrade", "--source", str(source), "--dry-run"],
    ))
    assert preview["dry_run"] is True
    assert preview["new_commit"] == first
    assert preview["history"]["status"] == "no_current_version"
    (source / "skills" / "mdf" / "SKILL.md").write_text("moved\n", encoding="utf-8")
    commit_all(source, "test: 上游前进")
    rejected = error(invoke(
        home, [sys.executable, "-B", str(source / "skills/mdf/scripts/mdf_launcher.py"),
               "upgrade", "--source", str(source), "--expected-commit", first],
    ))
    assert rejected["error"] == "upgrade_source_changed"
    assert not (home / ".local" / "share" / "mdf" / "current").exists()


def test_upgrade_installs_and_rolls_back_a_broken_payload(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    launcher = source / "skills/mdf/scripts/mdf_launcher.py"
    first = head(source)
    installed = payload(invoke(
        home, [sys.executable, "-B", str(launcher), "upgrade",
               "--source", str(source), "--expected-commit", first],
    ))
    assert installed["revision"] == first
    root = home / ".local" / "share" / "mdf"
    assert os.readlink(root / "current") == f"versions/{first}"
    assert_host_copies(home, root / "versions" / first)
    host_skill = source / "skills" / "mdf" / "assets" / "host" / "SKILL.md"
    host_skill.write_text(host_skill.read_text(encoding="utf-8") + "\nBROKEN-HOST\n", encoding="utf-8")
    (source / "skills" / "mdf" / "scripts" / "mdf.py").write_text(
        "import sys\nraise SystemExit(1)\n", encoding="utf-8",
    )
    commit_all(source, "test: 损坏入口")
    broken = head(source)
    failed = error(invoke(
        home, [sys.executable, "-B", str(root / "current" / "scripts" / "mdf_launcher.py"),
               "upgrade", "--source", str(source), "--expected-commit", broken],
    ))
    assert failed["error"] == "install_self_check_failed"
    assert os.readlink(root / "current") == f"versions/{first}"
    assert not (root / "versions" / broken).exists()
    assert "BROKEN-HOST" not in (home / ".agents/skills/mdf/SKILL.md").read_text(encoding="utf-8")
    assert_host_copies(home, root / "versions" / first)


def test_host_shell_rolls_back_when_a_later_host_write_fails(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    launcher = source / "skills/mdf/scripts/mdf_launcher.py"
    first = head(source)
    assert invoke(
        home, [sys.executable, "-B", str(launcher), "upgrade",
               "--source", str(source), "--expected-commit", first],
    ).returncode == 0
    root = home / ".local" / "share" / "mdf"
    host_skill = source / "skills" / "mdf" / "assets" / "host" / "SKILL.md"
    host_skill.write_text(host_skill.read_text(encoding="utf-8") + "\nHOST-NEW\n", encoding="utf-8")
    commit_all(source, "test: 更新引导壳")
    second = head(source)
    claude = home / ".claude"
    shutil.rmtree(claude)
    claude.write_text("block\n", encoding="utf-8")
    failed = error(invoke(
        home, [sys.executable, "-B", str(root / "current" / "scripts" / "mdf_launcher.py"),
               "upgrade", "--source", str(source), "--expected-commit", second],
    ))
    assert failed["error"] == "host_update_failed"
    assert os.readlink(root / "current") == f"versions/{first}"
    assert not (root / "versions" / second).exists()
    assert claude.read_text(encoding="utf-8") == "block\n"
    assert "HOST-NEW" not in (home / ".agents/skills/mdf/SKILL.md").read_text(encoding="utf-8")
    for folder in (".agents", ".kiro", ".openclaw"):
        path = home / folder / "skills" / "mdf" / "SKILL.md"
        assert path.is_file() and not path.is_symlink()
        assert path.read_bytes() == (root / "versions" / first / "assets/host/SKILL.md").read_bytes()


def test_upgrade_works_when_the_old_core_is_broken(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    first = head(source)
    launcher = source / "skills/mdf/scripts/mdf_launcher.py"
    assert invoke(
        home, [sys.executable, "-B", str(launcher), "upgrade",
               "--source", str(source), "--expected-commit", first],
    ).returncode == 0
    root = home / ".local" / "share" / "mdf"
    old = root / "versions" / first / "scripts" / "mdf_core" / "cli.py"
    old.unlink()
    host_skill = source / "skills" / "mdf" / "assets" / "host" / "SKILL.md"
    host_skill.write_text(host_skill.read_text(encoding="utf-8") + "\nSECOND-HOST\n", encoding="utf-8")
    new_launcher = source / "skills" / "mdf" / "scripts" / "mdf_launcher.py"
    new_launcher.write_text(new_launcher.read_text(encoding="utf-8") + "\n# second-host\n", encoding="utf-8")
    (source / "skills" / "mdf" / "SKILL.md").write_text("repaired\n", encoding="utf-8")
    commit_all(source, "test: 修复")
    second = head(source)
    upgraded = payload(invoke(
        home, [sys.executable, "-B", str(root / "versions" / first / "scripts" / "mdf_launcher.py"),
               "upgrade", "--source", str(source), "--expected-commit", second],
    ))
    assert upgraded["revision"] == second
    assert os.readlink(root / "current") == f"versions/{second}"
    assert (root / "versions" / second / "scripts" / "mdf_core" / "cli.py").is_file()
    assert_host_copies(home, root / "versions" / second)
    assert "SECOND-HOST" in (home / ".agents/skills/mdf/SKILL.md").read_text(encoding="utf-8")
    assert b"# second-host" in (home / ".agents/skills/mdf/scripts/mdf_launcher.py").read_bytes()


def test_restore_repairs_a_dangling_current(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    first = head(source)
    launcher = source / "skills/mdf/scripts/mdf_launcher.py"
    assert invoke(
        home, [sys.executable, "-B", str(launcher), "upgrade",
               "--source", str(source), "--expected-commit", first],
    ).returncode == 0
    root = home / ".local" / "share" / "mdf"
    (root / "current").unlink()
    (root / "current").symlink_to(Path("versions") / ("c" * 40))
    restored = payload(invoke(
        home, [sys.executable, "-B", str(root / "versions" / first / "scripts" / "mdf_launcher.py"),
               "restore", "--revision", first],
    ))
    assert restored["changed"] is True
    assert os.readlink(root / "current") == f"versions/{first}"
    assert_host_copies(home, root / "versions" / first)
    listed = payload(invoke(
        home, [sys.executable, "-B", str(root / "current" / "scripts" / "mdf_launcher.py"), "restore"],
    ))
    assert first in listed["versions"]
    assert listed["current"] == first


def test_failed_host_restore_still_restores_current_and_keeps_backup(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("mdf_home_under_test", SKILL / "scripts" / "mdf_home.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    root = tmp_path / "root"
    (root / "versions").mkdir(parents=True)
    for revision in (REV_A, REV_B):
        copy_skill(root / "versions" / revision)
        (root / "versions" / revision / "references" / ".version").write_text(
            f"{revision}\n", encoding="utf-8",
        )
    current = root / "current"
    current.symlink_to(Path("versions") / REV_A)
    module.install_hosts(root / "versions" / REV_A)
    skill = root / "versions" / REV_B / "assets" / "host" / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nHOST-NEW\n", encoding="utf-8")
    claude = home / ".claude"
    shutil.rmtree(claude)
    claude.write_text("block\n", encoding="utf-8")
    monkeypatch.setattr(module, "self_check", lambda *args: None)

    def fail_restore(backup):
        raise OSError("injected restore failure")

    monkeypatch.setattr(module, "_restore_hosts", fail_restore)
    with pytest.raises(module.HomeError) as info:
        module._activate(root, REV_B, created=True)
    assert info.value.code == "host_rollback_incomplete"
    assert os.readlink(root / "current") == f"versions/{REV_A}"
    backup = Path(info.value.details["backup"])
    assert backup.parent == root and backup.name.startswith(".host-backup-")
    assert backup.is_dir()
    assert (backup / "manifest.json").is_file()
    assert str(backup) in info.value.message
    assert info.value.details["backup"] == str(backup)
    assert "injected restore failure" in "；".join(info.value.details["rollback_failures"])
    assert not (root / "versions" / REV_B).exists()
    assert "HOST-NEW" in (home / ".agents/skills/mdf/SKILL.md").read_text(encoding="utf-8")


def test_failed_current_restore_keeps_version_and_backup(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("mdf_home_link_fail", SKILL / "scripts" / "mdf_home.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    root = tmp_path / "root"
    (root / "versions").mkdir(parents=True)
    for revision in (REV_A, REV_B):
        copy_skill(root / "versions" / revision)
        (root / "versions" / revision / "references" / ".version").write_text(
            f"{revision}\n", encoding="utf-8",
        )
    (root / "current").symlink_to(Path("versions") / REV_A)
    module.install_hosts(root / "versions" / REV_A)
    skill = root / "versions" / REV_B / "assets" / "host" / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nHOST-NEW\n", encoding="utf-8")
    claude = home / ".claude"
    shutil.rmtree(claude)
    claude.write_text("block\n", encoding="utf-8")

    def fail_link(target_root, previous):
        raise OSError("injected current restore failure")

    monkeypatch.setattr(module, "_restore_link", fail_link)
    with pytest.raises(module.HomeError) as info:
        module._activate(root, REV_B, created=True)
    version_dir = root / "versions" / REV_B
    assert info.value.code == "host_rollback_incomplete"
    assert os.readlink(root / "current") == f"versions/{REV_B}"
    assert version_dir.is_dir()
    backup = Path(info.value.details["backup"])
    assert backup.is_dir() and (backup / "manifest.json").is_file()
    assert info.value.details["version"] == str(version_dir)
    assert str(version_dir) in info.value.message and str(backup) in info.value.message
    assert "injected current restore failure" in "；".join(info.value.details["rollback_failures"])
    assert "HOST-NEW" not in (home / ".agents/skills/mdf/SKILL.md").read_text(encoding="utf-8")
    started = root_of(invoke(
        home, [sys.executable, "-B", str(home / ".agents/skills/mdf/scripts/mdf_launcher.py"), "root"],
        mdf_home=str(root),
    ))
    assert started == version_dir.resolve()
    claude.unlink()
    monkeypatch.undo()
    monkeypatch.setenv("HOME", str(home))
    module._activate(root, REV_A, created=False)
    assert os.readlink(root / "current") == f"versions/{REV_A}"
    assert backup.is_dir() and (backup / "manifest.json").is_file()


def test_clean_rollback_of_first_install_leaves_no_residue(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("mdf_home_first", SKILL / "scripts" / "mdf_home.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(module, "self_check", lambda *args: None)
    root = tmp_path / "first"
    (root / "versions").mkdir(parents=True)
    copy_skill(root / "versions" / REV_A)
    (home / ".claude").write_text("block\n", encoding="utf-8")
    with pytest.raises(module.HomeError) as info:
        module._activate(root, REV_A, created=True)
    assert info.value.code == "host_update_failed"
    assert not (root / "current").exists()
    assert not (root / "versions" / REV_A).exists()
    assert list(root.glob(".host-backup-*")) == []


IGNORE = ("/.mdf/logs/", "/.mdf/tmp/", "/.mdf/reports/", "/.mdf/cache/")


def make_project(path: Path, text: str = "node_modules/\n") -> Path:
    path.mkdir()
    (path / ".mdf").mkdir()
    (path / ".mdf" / "manifest.yaml").write_text("schema_version: 3\n", encoding="utf-8")
    (path / ".gitignore").write_text(text, encoding="utf-8")
    init_git(path)
    return path


def test_upgrade_adds_gitignore_block_to_repo(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = make_project(tmp_path / "repo")
    original = (repo / ".gitignore").read_text(encoding="utf-8")
    first = head(source)
    launcher = source / "skills/mdf/scripts/mdf_launcher.py"
    command = [
        sys.executable, "-B", str(launcher), "upgrade",
        "--source", str(source), "--expected-commit", first, "--repo", str(repo),
    ]
    installed = payload(invoke(home, command))
    assert installed["gitignore_added"] == list(IGNORE)
    text = (repo / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith(original)
    for line in IGNORE:
        assert text.count(line) == 1
    again = payload(invoke(home, command))
    assert again["gitignore_added"] == []
    assert (repo / ".gitignore").read_text(encoding="utf-8") == text


def test_upgrade_uses_cwd_repo_when_omitted(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = make_project(tmp_path / "repo", "keep\n")
    nested = repo / "src"
    nested.mkdir()
    first = head(source)
    installed = payload(invoke(
        home, [sys.executable, "-B", str(source / "skills/mdf/scripts/mdf_launcher.py"),
               "upgrade", "--source", str(source), "--expected-commit", first],
        cwd=nested,
    ))
    assert Path(installed["repo"]) == repo.resolve()
    text = (repo / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith("keep\n")
    for line in IGNORE:
        assert line in text


def test_upgrade_without_repo_skips_gitignore(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    first = head(source)
    installed = payload(invoke(
        home, [sys.executable, "-B", str(source / "skills/mdf/scripts/mdf_launcher.py"),
               "upgrade", "--source", str(source), "--expected-commit", first],
        cwd=tmp_path,
    ))
    assert installed["repo"] is None
    assert installed["gitignore_added"] == []
    assert not (tmp_path / ".gitignore").exists()


def test_upgrade_dry_run_does_not_touch_gitignore(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = make_project(tmp_path / "repo", "keep\n")
    before = (repo / ".gitignore").read_bytes()
    preview = payload(invoke(
        home, [sys.executable, "-B", str(source / "skills/mdf/scripts/mdf_launcher.py"),
               "upgrade", "--source", str(source), "--dry-run", "--repo", str(repo)],
    ))
    assert "gitignore_added" not in preview
    assert (repo / ".gitignore").read_bytes() == before


def test_upgrade_rejects_explicit_non_mdf_repo(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    (other / "README.md").write_text("plain\n", encoding="utf-8")
    init_git(other)
    failed = error(invoke(
        home, [sys.executable, "-B", str(source / "skills/mdf/scripts/mdf_launcher.py"),
               "upgrade", "--source", str(source), "--dry-run", "--repo", str(other)],
    ))
    assert failed["error"] == "upgrade_repo_invalid"
    assert not (home / ".local" / "share" / "mdf" / "current").exists()


def test_upgrade_rejects_gitignore_symlink_before_switch(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = make_project(tmp_path / "repo")
    outside = tmp_path / "outside-ignore"
    outside.write_text("secret\n", encoding="utf-8")
    ignore = repo / ".gitignore"
    ignore.unlink()
    ignore.symlink_to(outside)
    first = head(source)
    failed = error(invoke(
        home, [sys.executable, "-B", str(source / "skills/mdf/scripts/mdf_launcher.py"),
               "upgrade", "--source", str(source), "--expected-commit", first,
               "--repo", str(repo)],
    ))
    assert failed["error"] == "managed_symlink"
    assert outside.read_text(encoding="utf-8") == "secret\n"
    assert not (home / ".local" / "share" / "mdf" / "current").exists()
