"""薄入口：缺本修订的项目本体时自动拉取安装，再执行 root。"""
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

REVISION = ""
SOURCE = ""


def fail(code: str, message: str) -> None:
    print(message, file=sys.stderr)
    print(json.dumps({"ok": False, "error": code, "message": message}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(1)


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
        payload = fetch_payload(temp)
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
