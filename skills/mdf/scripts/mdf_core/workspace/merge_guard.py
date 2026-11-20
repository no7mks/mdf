"""固定实际 merge 的双亲，在 Git 写 target ref 前保留原 hooks 并复核快照。"""
import os
from pathlib import Path
import shlex
import sys
import tempfile

from mdf_core.foundation.errors import MDFError
from mdf_core.workspace.merge_policy import git, sha


def capture(repo, source, target):
    return {"source": source, "head": sha(repo, source), "target": target,
            "target_head": sha(repo, f"refs/heads/{target}")}


def require_snapshot(repo, snapshot):
    expected = ((snapshot["source"], snapshot["head"]),
                (f"refs/heads/{snapshot['target']}", snapshot["target_head"]))
    for ref, wanted in expected:
        current = git(repo, "rev-parse", "--verify", ref, check=False)
        if current.returncode or current.stdout.strip() != wanted:
            raise MDFError("source 或 target 在验收后前进，继续 incremental-integration 后重试 merge",
                           code="integration_required")


def commit_merge(repo, snapshot, message):
    require_snapshot(repo, snapshot)
    snapshot["tree"] = git(repo, "write-tree").stdout.strip()
    original = Path(git(repo, "rev-parse", "--git-path", "hooks").stdout.strip())
    if not original.is_absolute():
        original = (repo / original).resolve()
    with tempfile.TemporaryDirectory(prefix="mdf-merge-hooks-") as folder:
        hooks = Path(folder) / "hooks"
        hooks.mkdir()
        originals = {item.name: item for item in original.iterdir()
                     if item.is_file() and os.access(item, os.X_OK) and not item.name.endswith(".sample")} if original.is_dir() else {}
        guarded = {"pre-commit", "prepare-commit-msg", "commit-msg"}
        script = Path(folder) / "guard.py"
        script.write_text(_HOOK.replace("CONFIG", repr(snapshot)), encoding="utf-8")
        check = " ".join(shlex.quote(value) for value in (sys.executable, str(script)))
        # 无原 hook 时只需最后的 commit-msg guard；Git 仍用调用前 HEAD 做 ref CAS。
        for name in originals.keys() | {"commit-msg"}:
            body = "#!/bin/sh\n"
            if name in guarded:
                if name in originals:
                    body += check + " || exit $?\n"
                    body += shlex.quote(str(originals[name])) + ' "$@" || exit $?\n'
                body += "exec " + check + "\n"
            else:
                body += "exec " + shlex.quote(str(originals[name])) + ' "$@"\n'
            hook = hooks / name
            hook.write_text(body)
            hook.chmod(0o755)
        result = git(repo, "-c", f"core.hooksPath={hooks}", "commit", "-m", message, check=False)
        if result.returncode:
            require_snapshot(repo, snapshot)
            raise MDFError(result.stderr.strip() or "合并提交失败；保留 merge 现场", code="command_failed")
    rows = git(repo, "rev-list", "--first-parent", "--merges", "--parents", snapshot["target"]).stdout.splitlines()
    merged = next((parts[0] for row in rows if (parts := row.split())[1:]
                   == [snapshot["target_head"], snapshot["head"]]), None)
    if merged is None or git(repo, "rev-parse", f"{merged}^{{tree}}").stdout.strip() != snapshot["tree"]:
        raise MDFError("无法核对本次 merge 的固定双亲与内容；保留现场", code="integration_required")


_HOOK = r'''import subprocess
import sys

config = CONFIG


def read(ref):
    result = subprocess.run(["git", "rev-parse", "--verify", ref], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def check():
    branch = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], capture_output=True, text=True)
    valid = (branch.returncode == 0 and branch.stdout.strip() == "refs/heads/" + config["target"]
             and read("HEAD") == config["target_head"]
             and read("MERGE_HEAD") == config["head"]
             and read(config["source"]) == config["head"])
    tree = subprocess.run(["git", "write-tree"], capture_output=True, text=True)
    valid = valid and tree.returncode == 0 and tree.stdout.strip() == config["tree"]
    if not valid:
        sys.stderr.write("source、target 或 merge 内容在验收后改变；保留 merge 现场\n")
        sys.exit(1)


check()
'''
