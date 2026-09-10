"""Install-tree upgrade for the published MDF skill."""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from .errors import MDFError, emit
from .gitutil import repo_path, require_git_root
from .paths import relative

DEFAULT_SKILL_SOURCE = "http://10.1.5.65:8929/mars/mdf"
KNOWN_SKILL_DIRS = (
    ".agents/skills",
    ".claude/skills",
    ".codex/skills",
    ".cursor/skills",
    ".kiro/skills",
    ".openclaw/skills",
)
SOURCE_SKILL = "skills/mdf"


def _clone(source: str, dest: Path) -> None:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    completed = subprocess.run(
        ["git", "clone", "--depth", "1", "--", source, str(dest)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )
    if completed.returncode:
        raise MDFError(
            completed.stderr.strip() or f"git clone failed: {source}",
            code="upgrade_clone_failed",
        )


def _git_text(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise MDFError(
            completed.stderr.strip() or f"Command failed: {' '.join(args)}",
            code="command_failed",
        )
    return completed.stdout.strip()


def _archive_skill(clone: Path, commit: str) -> bytes:
    completed = subprocess.run(
        ["git", "archive", "--format=tar", f"{commit}:{SOURCE_SKILL}"],
        cwd=clone,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise MDFError(
            completed.stderr.strip() or "git archive failed",
            code="upgrade_archive_failed",
        )
    return completed.stdout


def _extract_tar(data: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        kwargs: dict[str, object] = {}
        if sys.version_info >= (3, 12):
            kwargs["filter"] = "data"
        tar.extractall(dest, **kwargs)


def _read_version(skill: Path) -> str | None:
    path = skill / "references" / ".version"
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    text = lines[0].strip() if lines else ""
    return text or None


def _installed_skills(repo: Path) -> list[Path]:
    found: list[Path] = []
    for directory in KNOWN_SKILL_DIRS:
        skill = repo / directory / "mdf"
        if not skill.exists() and not skill.is_symlink():
            continue
        if skill.is_symlink() or not skill.is_dir():
            raise MDFError(
                f"Installed mdf is not a directory: {relative(repo, skill)}",
                code="upgrade_not_dir",
            )
        found.append(skill)
    if not found:
        raise MDFError(
            "No installed mdf skill found in Agent skills directories",
            code="upgrade_no_install",
        )
    return found


def _write_version(skill: Path, commit: str) -> None:
    path = skill / "references" / ".version"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{commit}\n", encoding="utf-8")


def _replace_skill(dest: Path, payload: Path, commit: str) -> None:
    parent = dest.parent
    staging = parent / ".mdf-skill-new"
    backup = parent / ".mdf-skill-old"
    if staging.exists():
        shutil.rmtree(staging)
    if backup.exists():
        shutil.rmtree(backup)
    shutil.copytree(payload, staging)
    _write_version(staging, commit)
    dest.rename(backup)
    try:
        staging.rename(dest)
    except OSError:
        backup.rename(dest)
        raise
    shutil.rmtree(backup)


def _fetch(source: str) -> tuple[str, Path, tempfile.TemporaryDirectory[str]]:
    temp = tempfile.TemporaryDirectory()
    clone = Path(temp.name) / "source"
    try:
        _clone(source, clone)
        commit = _git_text(["git", "rev-parse", "HEAD"], clone)
        skill = clone / SOURCE_SKILL
        if not skill.is_dir():
            raise MDFError(
                f"Upstream is missing {SOURCE_SKILL}",
                code="upgrade_missing_skill",
            )
    except Exception:
        temp.cleanup()
        raise
    return commit, clone, temp


def command_upgrade(args: argparse.Namespace) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    source = args.source
    installs = _installed_skills(repo)
    commit, clone, temp = _fetch(source)
    try:
        targets = [
            {
                "path": relative(repo, skill),
                "current_commit": _read_version(skill),
            }
            for skill in installs
        ]
        payload = {
            "ok": True,
            "operation": "upgrade",
            "dry_run": bool(args.dry_run),
            "source": source,
            "new_commit": commit,
            "targets": targets,
        }
        if args.dry_run:
            emit(payload)
            return
        archive = _archive_skill(clone, commit)
        with tempfile.TemporaryDirectory() as extracted_root:
            extracted = Path(extracted_root) / "skill"
            _extract_tar(archive, extracted)
            if not (extracted / "SKILL.md").is_file():
                raise MDFError(
                    "Archived skill is missing SKILL.md",
                    code="upgrade_missing_skill",
                )
            for skill in installs:
                _replace_skill(skill, extracted, commit)
        payload["replaced"] = [item["path"] for item in targets]
        emit(payload)
    finally:
        temp.cleanup()
