"""MDF Deploy 的基线比较、安装和卸载。"""

from __future__ import annotations

import shutil
from pathlib import Path

from _support import REPO_ROOT, run
from mdf_test_support import init_git


SCRIPT = REPO_ROOT / "mdf-deploy.sh"
SKILL = REPO_ROOT / ".agents" / "skills" / "mdf-deploy" / "SKILL.md"


def command(script: Path, target: Path, action: str):
    return run(["sh", str(script), action, "--target", str(target)])


def init_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    (source / "skills").mkdir(parents=True)
    shutil.copy2(SCRIPT, source / "mdf-deploy.sh")
    shutil.copytree(REPO_ROOT / "skills" / "mdf", source / "skills" / "mdf")
    init_git(source)
    return source


def init_target(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("# target\n", encoding="utf-8")
    (target / ".codex" / "skills").mkdir(parents=True)
    init_git(target)
    return target


def test_internal_skill_lists_the_three_commands() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "name: mdf-deploy" in text
    assert 'mdf-deploy.sh" merge' not in text
    assert not (REPO_ROOT / "redeploy_mdf.sh").exists()
    assert not (REPO_ROOT / ".agents" / "skills" / "mdf-redeploy").exists()
    for action in ("diff", "install", "unistall"):
        assert f" {action} " in text


def test_script_rejects_removed_merge() -> None:
    result = run(["sh", str(SCRIPT), "merge"])

    assert result.returncode != 0
    assert "未知动作: merge" in result.stderr


def test_install_archives_head_and_writes_baseline(tmp_path: Path) -> None:
    source = init_source(tmp_path)
    target = init_target(tmp_path)

    result = command(source / "mdf-deploy.sh", target, "install")

    assert result.returncode == 0, result.stderr
    installed = target / ".codex" / "skills" / "mdf"
    version = run([
        "git",
        "-C",
        str(source),
        "rev-parse",
        "HEAD",
    ]).stdout.strip()
    assert (installed / "references" / ".version").read_text() == f"{version}\n"
    assert (installed / "SKILL.md").read_text() == (
        source / "skills" / "mdf" / "SKILL.md"
    ).read_text()


def test_install_requires_clean_source_worktree(tmp_path: Path) -> None:
    source = init_source(tmp_path)
    target = init_target(tmp_path)
    (source / "skills" / "mdf" / "SKILL.md").write_text("changed\n")

    result = command(source / "mdf-deploy.sh", target, "install")

    assert result.returncode != 0
    assert "工作区不干净" in result.stderr
    assert not (target / ".codex" / "skills" / "mdf").exists()


def test_install_stops_when_target_already_has_mdf(tmp_path: Path) -> None:
    source = init_source(tmp_path)
    target = init_target(tmp_path)

    first_install = command(source / "mdf-deploy.sh", target, "install")
    assert first_install.returncode == 0
    repeated = command(source / "mdf-deploy.sh", target, "install")

    assert repeated.returncode != 0
    assert "目标已安装 mdf" in repeated.stderr


def test_diff_compares_local_and_target_against_baseline(
    tmp_path: Path,
) -> None:
    source = init_source(tmp_path)
    target = init_target(tmp_path)
    script = source / "mdf-deploy.sh"

    assert command(script, target, "install").returncode == 0
    (source / "skills" / "mdf" / "local.md").write_text("local\n")
    installed = target / ".codex" / "skills" / "mdf"
    (installed / "target.md").write_text("target\n")

    result = command(script, target, "diff")

    assert result.returncode == 0, result.stderr
    assert "本地相对基线" in result.stdout
    assert "local.md" in result.stdout
    assert "目标相对基线" in result.stdout
    assert "target.md" in result.stdout


def test_diff_requires_an_install_baseline(tmp_path: Path) -> None:
    source = init_source(tmp_path)
    target = init_target(tmp_path)
    (target / ".codex" / "skills" / "mdf").mkdir()

    result = command(source / "mdf-deploy.sh", target, "diff")

    assert result.returncode != 0
    assert "缺少 references/.version" in result.stderr


def test_unistall_only_removes_target_mdf(tmp_path: Path) -> None:
    source = init_source(tmp_path)
    target = init_target(tmp_path)
    script = source / "mdf-deploy.sh"
    assert command(script, target, "install").returncode == 0

    result = command(script, target, "unistall")

    assert result.returncode == 0, result.stderr
    assert not (target / ".codex" / "skills" / "mdf").exists()
