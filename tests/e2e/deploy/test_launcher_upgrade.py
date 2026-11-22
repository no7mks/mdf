"""仓外升级：预览、回滚，以及旧 Core 损坏时仍能升级。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from _support import run
from launcher_support import assert_host_copies, error, invoke, payload, upstream
from mdf_test_support import git


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
