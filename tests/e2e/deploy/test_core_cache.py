"""项目里只有一份 MDF 本体，升级替换它，失败时不动 current。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from launcher_support import (
    SKILL,
    assert_pointer,
    core_dir,
    error,
    invoke,
    payload,
    upstream,
)
from mdf_test_support import git, init_git


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "--all")
    git(repo, "commit", "-m", message)


def launcher_of(source: Path) -> Path:
    return source / "skills/mdf/scripts/mdf_launcher.py"


def upgrade(home: Path, source: Path, repo: Path, commit: str, *, dry_run: bool = False, cwd: Path | None = None):
    args = [
        sys.executable, "-B", str(launcher_of(source)), "upgrade",
        "--source", str(source), "--repo", str(repo),
    ]
    if dry_run:
        args.append("--dry-run")
    else:
        args.extend(["--expected-commit", commit])
    return invoke(home, args, cwd=cwd or repo)


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if item.is_file() and not item.is_symlink():
            digest.update(item.relative_to(path).as_posix().encode())
            digest.update(item.read_bytes())
    return digest.hexdigest()


def test_first_install_keeps_one_untracked_copy(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    commit = head(source)
    installed = payload(upgrade(home, source, repo, commit))
    current = core_dir(repo) / commit
    assert current.is_dir() and not current.is_symlink()
    assert (current / "references" / ".version").read_text(encoding="utf-8").startswith(commit)
    assert {path.name for path in core_dir(repo).iterdir()} == {commit, ".lock"}
    assert installed["root"] == str(current.resolve())
    status = git(repo, "status", "--porcelain").stdout
    assert ".gitignore" in status
    assert ".mdf/" not in status
    assert list((repo / ".mdf" / "logs").glob("*-install-*.json"))
    assert not home.exists()
    assert ".agents/" not in status
    assert_pointer(repo, commit, str(source))


def test_dry_run_does_not_create_current_or_gitignore(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    preview = payload(upgrade(home, source, repo, head(source), dry_run=True))
    assert preview["dry_run"] is True
    assert not core_dir(repo).exists()
    assert not (repo / ".gitignore").exists()
    assert not (repo / ".agents").exists()
    (source / "skills" / "mdf" / "SKILL.md").write_text("moved\n", encoding="utf-8")
    commit_all(source, "test: 上游前进")
    rejected = error(upgrade(home, source, repo, preview["new_commit"]))
    assert rejected["error"] == "upgrade_source_changed", rejected


def test_second_upgrade_drops_the_old_tree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    first = head(source)
    assert upgrade(home, source, repo, first).returncode == 0
    marker = core_dir(repo) / first / "OLD-MARKER"
    marker.write_text("old\n", encoding="utf-8")
    (source / "skills" / "mdf" / "SKILL.md").write_text("second\n", encoding="utf-8")
    commit_all(source, "test: 第二版")
    second = head(source)
    assert upgrade(home, source, repo, second).returncode == 0
    current = core_dir(repo) / second
    assert not (core_dir(repo) / first).exists()
    assert not marker.exists()
    assert (current / "references" / ".version").read_text(encoding="utf-8").startswith(second)
    assert {path.name for path in core_dir(repo).iterdir()} == {second, ".lock"}
    assert_pointer(repo, second, str(source))


def test_failed_self_check_leaves_current_unchanged(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    first = head(source)
    assert upgrade(home, source, repo, first).returncode == 0
    current = core_dir(repo) / first
    before = tree_hash(current)
    host_before = {
        path: path.read_bytes()
        for path in (repo / ".agents" / "skills" / "mdf").rglob("*")
        if path.is_file()
    }
    (source / "skills" / "mdf" / "scripts" / "mdf.py").write_text(
        "import sys\nraise SystemExit(1)\n", encoding="utf-8",
    )
    commit_all(source, "test: 损坏入口")
    failed = error(upgrade(home, source, repo, head(source)))
    assert failed["error"] == "install_self_check_failed"
    assert tree_hash(current) == before
    assert not (core_dir(repo) / head(source)).exists()
    assert not list(core_dir(repo).glob(".staging-*"))
    host_after = {
        path: path.read_bytes()
        for path in (repo / ".agents" / "skills" / "mdf").rglob("*")
        if path.is_file()
    }
    assert host_after == host_before


def test_upgrade_from_source_replaces_a_broken_current(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    commit = head(source)
    assert upgrade(home, source, repo, commit).returncode == 0
    broken = core_dir(repo) / commit / "scripts" / "mdf_core" / "cli.py"
    broken.unlink()
    assert upgrade(home, source, repo, commit).returncode == 0
    assert broken.is_file()


def test_exchange_failure_keeps_current_and_drops_staging(tmp_path: Path, monkeypatch) -> None:
    import mdf_home
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "repo"
    project.mkdir()
    payload_dir = tmp_path / "payload"
    shutil.copytree(SKILL, payload_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    old = "a" * 40
    revision = "c" * 40
    source_url = "https://github.com/no7mks/mdf.git"
    assert mdf_home.install_payload(project, old, payload_dir, source_url)["revision"] == old
    before = tree_hash(core_dir(project) / old)
    host_before = (project / ".agents" / "skills" / "mdf" / "mdf_entry.py").read_bytes()
    real_rename = os.rename

    def fail_rename(src, dst):
        if Path(dst).name == revision:
            raise OSError("rename failed")
        real_rename(src, dst)

    monkeypatch.setattr(os, "rename", fail_rename)
    with pytest.raises(mdf_home.HomeError):
        mdf_home.install_payload(project, revision, payload_dir, source_url)
    assert tree_hash(core_dir(project) / old) == before
    assert not (core_dir(project) / revision).exists()
    assert not list(core_dir(project).glob(".staging-*"))
    assert (project / ".agents" / "skills" / "mdf" / "mdf_entry.py").read_bytes() == host_before


def test_host_pointer_replaces_the_whole_directory(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    leftover = repo / ".agents" / "skills" / "mdf" / "scripts"
    leftover.mkdir(parents=True)
    (leftover / "mdf_home.py").write_text("old\n", encoding="utf-8")
    commit = head(source)
    assert upgrade(home, source, repo, commit).returncode == 0
    assert_pointer(repo, commit, str(source))
    assert not leftover.exists()


def test_root_only_accepts_the_project_cache(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    commit = head(source)
    assert upgrade(home, source, repo, commit).returncode == 0
    current = core_dir(repo) / commit
    found = invoke(
        home, [sys.executable, "-B", str(current / "scripts" / "mdf_launcher.py"), "root"],
        cwd=repo,
    )
    assert found.returncode == 0
    assert found.stdout.strip() == str(current.resolve())
    rejected = error(invoke(
        home, [sys.executable, "-B", str(launcher_of(source)), "root"], cwd=repo,
    ))
    assert rejected["error"] == "mdf_core_invalid"


def test_repo_discovery_uses_the_main_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    nested = repo / "src"
    nested.mkdir()
    commit = head(source)
    rejected = error(upgrade(home, source, nested, commit))
    assert rejected["error"] == "upgrade_repo_invalid"
    found = payload(invoke(
        home, [sys.executable, "-B", str(launcher_of(source)), "upgrade",
               "--source", str(source), "--expected-commit", commit],
        cwd=nested,
    ))
    assert Path(found["repo"]) == repo.resolve()
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "--detach", str(linked))
    rejected = error(invoke(
        home, [sys.executable, "-B", str(launcher_of(source)), "upgrade",
               "--source", str(source), "--dry-run"],
        cwd=linked,
    ))
    assert rejected["error"] == "upgrade_repo_invalid"
    outside = error(invoke(
        home, [sys.executable, "-B", str(launcher_of(source)), "upgrade", "--dry-run"],
        cwd=tmp_path,
    ))
    assert outside["error"] == "upgrade_repo_invalid"
    plain = tmp_path / "plain"
    plain.mkdir()
    plain_result = payload(upgrade(home, source, plain, commit))
    assert (core_dir(plain) / commit).is_dir()
    assert plain_result["repo"] == str(plain.resolve())


def test_symlink_targets_are_rejected_before_any_write(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".gitignore").symlink_to(outside / "ignore")
    failed = error(upgrade(home, source, repo, head(source)))
    assert failed["error"] == "managed_symlink"
    assert not (outside / "ignore").exists()
    assert not core_dir(repo).exists()
    (repo / ".gitignore").unlink()
    (repo / ".mdf" / "cache").mkdir(parents=True)
    (repo / ".mdf" / "cache").rmdir()
    (repo / ".mdf" / "cache").symlink_to(outside, target_is_directory=True)
    failed = error(upgrade(home, source, repo, head(source)))
    assert failed["error"] == "managed_symlink"
    assert list(outside.iterdir()) == []
    assert not (repo / ".gitignore").exists()


def test_removed_commands_are_argparse_errors(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    script = launcher_of(source)
    for args in (["restore"], ["upgrade", "--home", str(tmp_path)], ["info"]):
        result = invoke(home, [sys.executable, "-B", str(script), *args], cwd=tmp_path)
        assert result.returncode != 0
        assert "error:" in result.stderr


def test_mdf_home_is_ignored(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    decoy = tmp_path / "decoy"
    result = invoke(
        home, [sys.executable, "-B", str(launcher_of(source)), "upgrade",
               "--source", str(source), "--repo", str(repo),
               "--expected-commit", head(source)],
        cwd=repo, mdf_home=str(decoy),
    )
    assert result.returncode == 0
    assert not decoy.exists()
    assert (core_dir(repo) / head(source)).is_dir()


def test_detached_source_installs_that_commit(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    first = head(source)
    (source / "skills" / "mdf" / "SKILL.md").write_text("later\n", encoding="utf-8")
    commit_all(source, "test: 更新")
    git(source, "checkout", "--detach", first)
    installed = payload(upgrade(home, source, repo, first))
    text = (core_dir(repo) / first / "references" / ".version").read_text(encoding="utf-8")
    assert text.startswith(first)
    assert installed["revision"] == first


def test_dry_run_does_not_write_logs(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    (repo / ".mdf").mkdir()
    init_git(repo)
    preview = payload(upgrade(home, source, repo, head(source), dry_run=True))
    assert preview["log"] is None
    assert not (repo / ".mdf" / "logs").exists()
    assert not core_dir(repo).exists()


def test_project_entry_parent_symlink_is_not_followed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".agents").symlink_to(outside, target_is_directory=True)
    failed = error(upgrade(home, source, repo, head(source)))
    assert failed["error"] == "managed_symlink"
    assert not core_dir(repo).exists()
    assert not home.exists()
    assert list(outside.iterdir()) == []


def test_install_preserves_tracked_entry_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    skill = repo / ".agents/skills/mdf/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("tracked skill", encoding="utf-8")
    init_git(repo)
    failed = error(upgrade(home, source, repo, head(source)))
    assert failed["error"] == "entry_tracked"
    assert skill.read_text(encoding="utf-8") == "tracked skill"
    assert not core_dir(repo).exists()
    assert git(repo, "status", "--porcelain").stdout == ""


def test_file_current_is_replaced_without_staging(tmp_path: Path, monkeypatch) -> None:
    import mdf_home
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "repo"
    project.mkdir()
    payload_dir = tmp_path / "payload"
    shutil.copytree(SKILL, payload_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    revision = "d" * 40
    mdf_home.install_payload(project, revision, payload_dir, "https://github.com/no7mks/mdf.git")
    current = core_dir(project) / revision
    shutil.rmtree(current)
    current.write_text("broken\n", encoding="utf-8")
    mdf_home.install_payload(project, revision, payload_dir, "https://github.com/no7mks/mdf.git")
    assert current.is_dir()
    assert (current / "scripts" / "mdf.py").is_file()
    assert not list(core_dir(project).glob(".staging-*"))


def test_root_rejects_symlink_into_the_cache(tmp_path: Path, monkeypatch) -> None:
    import mdf_home
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "repo"
    project.mkdir()
    payload_dir = tmp_path / "payload"
    shutil.copytree(SKILL, payload_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    revision = "e" * 40
    mdf_home.install_payload(project, revision, payload_dir, "https://github.com/no7mks/mdf.git")
    current = core_dir(project) / revision
    via = tmp_path / "via"
    via.symlink_to(project, target_is_directory=True)
    found = mdf_home.core_of_launcher(via / ".mdf/cache/mdf-core" / revision / "scripts/mdf_launcher.py")
    assert found == current.resolve()
    real = tmp_path / "real-core"
    shutil.move(str(current), real)
    current.symlink_to(real, target_is_directory=True)
    with pytest.raises(mdf_home.HomeError) as info:
        mdf_home.core_of_launcher(current / "scripts" / "mdf_launcher.py")
    assert info.value.code == "mdf_core_invalid"


def test_leftover_staging_is_removed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    stale = core_dir(repo) / ".staging-x"
    stale.mkdir(parents=True)
    (stale / "junk").write_text("x\n", encoding="utf-8")
    commit = head(source)
    other = core_dir(repo) / ("b" * 40)
    other.mkdir()
    (other / "old").write_text("old\n", encoding="utf-8")
    assert upgrade(home, source, repo, commit).returncode == 0
    assert not stale.exists()
    assert not other.exists()
    assert {path.name for path in core_dir(repo).iterdir()} == {commit, ".lock"}


def test_missing_revision_dir_is_installed_on_start(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    init_git(repo)
    commit = head(source)
    assert upgrade(home, source, repo, commit).returncode == 0
    entry = repo / ".agents/skills/mdf/mdf_entry.py"
    shutil.rmtree(core_dir(repo) / commit)
    other = tmp_path / "other"
    other.mkdir()
    started = invoke(home, [sys.executable, "-B", str(entry)], cwd=other)
    assert started.returncode == 0, started.stderr
    assert started.stdout.strip() == str((core_dir(repo) / commit).resolve())
    assert {path.name for path in core_dir(repo).iterdir()} == {commit, ".lock"}
    assert list(other.iterdir()) == []


def test_project_upgrade_keeps_other_project_revision(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    first = head(source)
    left = tmp_path / "left"
    right = tmp_path / "right"
    for repo in (left, right):
        repo.mkdir()
        (repo / "README.md").write_text("app\n", encoding="utf-8")
        init_git(repo)
        assert upgrade(home, source, repo, first).returncode == 0
    (source / "skills" / "mdf" / "SKILL.md").write_text("second\n", encoding="utf-8")
    commit_all(source, "test: 第二版")
    second = head(source)
    assert upgrade(home, source, left, second).returncode == 0
    (source / "skills" / "mdf" / "SKILL.md").write_text("third\n", encoding="utf-8")
    commit_all(source, "test: 第三版")
    assert_pointer(left, second, str(source))
    assert_pointer(right, first, str(source))
    entry = right / ".agents/skills/mdf/mdf_entry.py"
    shutil.rmtree(core_dir(right) / first)
    started = invoke(home, [sys.executable, "-B", str(entry)], cwd=right)
    assert started.returncode == 0, started.stderr
    assert started.stdout.strip() == str((core_dir(right) / first).resolve())
    assert {path.name for path in core_dir(right).iterdir()} == {first, ".lock"}


def test_failed_publish_keeps_new_core_and_retry_only_publishes(tmp_path: Path, monkeypatch) -> None:
    import mdf_home
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "repo"
    project.mkdir()
    payload_dir = tmp_path / "payload"
    shutil.copytree(SKILL, payload_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    source_url = "https://github.com/no7mks/mdf.git"
    old = "a" * 40
    new = "b" * 40
    mdf_home.install_payload(project, old, payload_dir, source_url)
    host_before = (project / ".agents" / "skills" / "mdf" / "mdf_entry.py").read_bytes()

    def fail_exchange(_src, _dest):
        raise OSError("引导目录交换失败")

    with monkeypatch.context() as patch:
        patch.setattr(mdf_home, "_exchange", fail_exchange)
        with pytest.raises(mdf_home.HomeError) as info:
            mdf_home.install_payload(project, new, payload_dir, source_url)
    assert info.value.code == "host_update_failed"
    assert (core_dir(project) / new / "scripts" / "mdf.py").is_file()
    assert (core_dir(project) / old).is_dir()
    assert (project / ".agents" / "skills" / "mdf" / "mdf_entry.py").read_bytes() == host_before
    assert not list((project / ".agents" / "skills").glob(".host-stage-*"))
    marker = core_dir(project) / new / "MARKER"
    marker.write_text("keep\n", encoding="utf-8")
    inode = (core_dir(project) / new).stat().st_ino
    calls = []
    real_copy = shutil.copytree

    def spy_copy(*args, **kwargs):
        calls.append(args)
        return real_copy(*args, **kwargs)

    monkeypatch.setattr(shutil, "copytree", spy_copy)
    mdf_home.install_payload(project, new, payload_dir, source_url)
    assert calls == []
    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert (core_dir(project) / new).stat().st_ino == inode
    text = (project / ".agents" / "skills" / "mdf" / "mdf_entry.py").read_text(encoding="utf-8")
    assert f"REVISION = {json.dumps(new)}" in text
    assert not (core_dir(project) / old).exists()


def test_unrendered_entry_template_refuses(tmp_path: Path) -> None:
    result = invoke(
        tmp_path / "home",
        [sys.executable, "-B", str(SKILL / "assets" / "host" / "mdf_entry.py")],
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert '"error": "entry_unrendered"' in result.stderr
    assert not (tmp_path / ".mdf").exists()
