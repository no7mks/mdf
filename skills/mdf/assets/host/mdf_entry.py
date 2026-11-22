"""薄入口：缺本修订的项目本体时自动补装，再执行 root。"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

try:
    import fcntl
except ImportError:  # 非 POSIX
    fcntl = None

REVISION = ""
SOURCE = ""


def fail(code: str, message: str) -> None:
    print(message, file=sys.stderr)
    print(json.dumps({"ok": False, "error": code, "message": message}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(1)


def main_worktree(root: Path) -> Path | None:
    result = subprocess.run(["git", "worktree", "list", "--porcelain", "-z"], cwd=root, capture_output=True)
    if result.returncode:
        return None
    record = result.stdout.split(b"\0\0", 1)[0].split(b"\0")
    prefix = b"worktree "
    if not record[0].startswith(prefix) or b"bare" in record[1:]:
        return None
    main = Path(os.fsdecode(record[0][len(prefix):])).resolve()
    return main if main != root else None


def cached_payload(root: Path, temp: Path) -> Path | None:
    if fcntl is None:
        return None
    snapshot = temp / "cached-skill"
    try:
        main = main_worktree(root)
        if main is None:
            return None
        core = main / ".mdf/cache/mdf-core"
        lock = core / ".lock"
        if any(path.is_symlink() for path in (lock, core, *core.parents[:2])) or not lock.is_file():
            return None
        with lock.open("rb") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            candidate = core / REVISION
            version = candidate / "references/.version"
            if any(path.is_symlink() for path in (candidate, version.parent, version)) or not version.is_file():
                return None
            with version.open(encoding="utf-8") as marker:
                if marker.readline().strip() != REVISION:
                    return None
            shutil.copytree(candidate, snapshot, symlinks=True)
        if any(path.is_symlink() for path in snapshot.rglob("*")):
            return None
    except (OSError, UnicodeError):
        return None
    checked = subprocess.run(
        [sys.executable, "-B", str(snapshot / "scripts/mdf_launcher.py"), "check-payload",
         "--revision", REVISION, "--log-dir", str(temp / "logs")],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    if checked.returncode == 0 and checked.stdout == f"{REVISION}\n".encode():
        return snapshot
    return None


def fetch_payload(temp: Path) -> Path:
    repo = temp / "source"
    repo.mkdir()
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    init = subprocess.run(["git", "init", "--quiet"], cwd=repo, env=env, capture_output=True, text=True)
    if init.returncode:
        fail("core_fetch_failed", init.stderr.strip() or "git init 失败")
    fetched = subprocess.run(
        ["git", "fetch", "--depth", "1", "--no-tags", "--", SOURCE, REVISION],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    if fetched.returncode:
        fail("core_fetch_failed", fetched.stderr.strip() or "git fetch 失败")
    archive = subprocess.run(
        ["git", "archive", f"{REVISION}:skills/mdf"],
        cwd=repo, env=env, capture_output=True,
    )
    if archive.returncode:
        detail = archive.stderr.decode().strip()
        fail("core_fetch_failed", detail or "git archive 失败")
    payload = temp / "skill"
    payload.mkdir()
    kwargs = {"filter": "data"} if sys.version_info >= (3, 12) else {}
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        tar.extractall(payload, **kwargs)
    return payload


def install(root: Path, launcher: Path) -> None:
    temp = Path(tempfile.mkdtemp(prefix="mdf-entry-"))
    try:
        payload = cached_payload(root, temp) or fetch_payload(temp)
        installed = payload / "scripts" / "mdf_launcher.py"
        completed = subprocess.run(
            [
                sys.executable, "-B", str(installed), "install-payload", "--from-entry",
                "--revision", REVISION, "--payload", str(payload),
                "--repo", str(root), "--source", SOURCE,
            ],
            stdout=subprocess.DEVNULL,
        )
        if completed.returncode:
            raise SystemExit(completed.returncode)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    if not launcher.is_file():
        fail("core_fetch_failed", "安装后仍没有本体")


def main() -> None:
    if not REVISION or not SOURCE:
        fail("entry_unrendered", "薄入口尚未写入修订号")
    root = Path(__file__).resolve().parents[3]
    launcher = root / ".mdf" / "cache" / "mdf-core" / REVISION / "scripts" / "mdf_launcher.py"
    if not launcher.is_file():
        install(root, launcher)
    raise SystemExit(subprocess.run([sys.executable, "-B", str(launcher), "root"]).returncode)


if __name__ == "__main__":
    main()
