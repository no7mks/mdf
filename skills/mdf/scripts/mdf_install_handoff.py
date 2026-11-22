"""完成已确认的仓内 Skill 替换，交接到项目缓存。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import mdf_home
from mdf_core.workspace.detach import HOST_COPIES


def _copy_paths(project: Path, revision: str, payload: Path) -> list[str]:
    copies = []
    for relative in HOST_COPIES:
        if not mdf_home._git_text(["git", "ls-files", "--", relative], project):
            continue
        directory = project / relative
        marker = directory / "references" / ".version"
        if any((project / part).is_symlink() for part in (Path(relative), *Path(relative).parents)):
            raise mdf_home.HomeError(f"{relative} 含 symbolic link", "handoff_invalid_copy")
        if not marker.is_file() or marker.is_symlink() or marker.read_text(encoding="utf-8").strip() != revision:
            raise mdf_home.HomeError(f"{relative} 未替换为已确认的修订", "handoff_invalid_copy")
        if mdf_home._git_text(["git", "status", "--porcelain", "--", relative], project):
            raise mdf_home.HomeError(f"{relative} 有本地修改或未跟踪文件", "handoff_dirty")
        untracked = mdf_home._git_text(["git", "ls-files", "--others", "--", relative], project)
        if any(Path(item).suffix != ".pyc" or "__pycache__" not in Path(item).parts for item in untracked.splitlines()):
            raise mdf_home.HomeError(f"{relative} 含额外的本地文件", "handoff_dirty")
        copies.append(relative)
    if payload not in {project / relative for relative in copies}:
        raise mdf_home.HomeError("接管来源必须是已替换的仓内 Skill", "handoff_invalid_copy")
    return copies


def handoff(repo: str, payload: Path, revision: str, source: str) -> dict:
    if not mdf_home.COMMIT_RE.fullmatch(revision):
        raise mdf_home.HomeError("接管需要已经确认的完整修订号", "invalid_revision")
    project = mdf_home._upgrade_repo(repo)
    mdf_home._git_text(["git", "rev-parse", "--show-toplevel"], project)
    payload = payload.resolve()
    copies = _copy_paths(project, revision, payload)
    entry_directory = project / mdf_home.ENTRY_DIR
    if mdf_home.ENTRY_DIR.as_posix() not in copies and (entry_directory.exists() or entry_directory.is_symlink()):
        raise mdf_home.HomeError(f"{entry_directory} 已存在，无法安全替换", "handoff_dirty")
    mdf_home.read_project_gitignore(project)
    ignore = project / ".gitignore"
    previous_ignore = ignore.read_bytes() if ignore.is_file() else None
    parked = Path(tempfile.mkdtemp(prefix=".mdf-handoff-", dir=project))
    moved: dict[str, Path] = {}
    removed_from_index = False
    try:
        for number, relative in enumerate(copies):
            backup = parked / str(number)
            os.rename(project / relative, backup)
            moved[relative] = backup
        mdf_home._git_text(["git", "rm", "--cached", "-r", "--", *copies], project)
        removed_from_index = True
        tree = moved[payload.relative_to(project).as_posix()]
        result = mdf_home.install_payload(project, revision, tree, source)
    except (mdf_home.HomeError, OSError) as exc:
        try:
            if removed_from_index:
                mdf_home._drop(entry_directory)
                mdf_home._git_text(["git", "restore", "--staged", "--", *copies], project)
                if previous_ignore is not None:
                    ignore.write_bytes(previous_ignore)
                else:
                    ignore.unlink(missing_ok=True)
            for relative, backup in reversed(moved.items()):
                os.rename(backup, project / relative)
        except (mdf_home.HomeError, OSError) as recovery:
            raise mdf_home.HomeError(
                f"接管失败：{exc}。恢复失败：{recovery}。备份保存在 {parked}", "handoff_recovery_failed",
            ) from recovery
        mdf_home._drop(parked)
        if isinstance(exc, mdf_home.HomeError):
            raise
        raise mdf_home.HomeError(f"接管失败：{exc}", "handoff_failed") from exc
    mdf_home._drop(parked)
    entry = entry_directory / "mdf_entry.py"
    return {**result, "operation": "complete-upgrade", "entry": str(entry), "detached": copies}
