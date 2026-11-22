"""已启动的调用保持原修订；之后的调用看到新的 current。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from launcher_support import invoke, payload, root_of, upstream
from mdf_test_support import git


def test_running_call_keeps_its_revision_after_current_switches(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = upstream(tmp_path)
    first = git(source, "rev-parse", "HEAD").stdout.strip()
    launcher = source / "skills" / "mdf" / "scripts" / "mdf_launcher.py"
    assert invoke(
        home, [sys.executable, "-B", str(launcher), "upgrade",
               "--source", str(source), "--expected-commit", first],
    ).returncode == 0
    root = home / ".local" / "share" / "mdf"
    second = "b" * 40
    shutil.copytree(root / "versions" / first, root / "versions" / second)
    (root / "versions" / second / "references" / ".version").write_text(
        f"{second}\n", encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    logs = tmp_path / "logs"
    flag = tmp_path / "release"
    env = os.environ.copy()
    env.update(HOME=str(home), MDF_LOG_DIR=str(logs), MDF_TEST_RELEASE=str(flag))
    env.pop("MDF_HOME", None)
    code = (
        "import os, time\n"
        "from pathlib import Path\n"
        "flag = Path(os.environ['MDF_TEST_RELEASE'])\n"
        "while not flag.exists():\n"
        "    time.sleep(0.05)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-B", str(root / "current" / "scripts" / "mdf_launcher.py"),
         "run", "--repo", str(repo), "--", sys.executable, "-c", code],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    deadline = time.time() + 20
    while time.time() < deadline and not list(logs.glob("*-run")):
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    assert list(logs.glob("*-run")), proc.stderr.read() if proc.poll() is not None else "log missing"
    restored = payload(invoke(
        home, [sys.executable, "-B", str(root / "versions" / first / "scripts" / "mdf_launcher.py"),
               "restore", "--revision", second],
    ))
    assert restored["revision"] == second
    flag.write_text("go\n", encoding="utf-8")
    stdout, stderr = proc.communicate(timeout=20)
    assert proc.returncode == 0, stderr
    meta = json.loads(next(logs.glob("*-run/meta.json")).read_text(encoding="utf-8"))
    assert meta["tool_revision"] == first
    assert meta["mdf_root"].endswith(f"versions/{first}")
    later = root_of(invoke(
        home, [sys.executable, "-B", str(root / "current" / "scripts" / "mdf_launcher.py"), "root"],
    ))
    assert later.name == second
    assert stdout
