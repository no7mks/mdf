"""用实际 pre-push 更新清单保证 release ref 参与原子发布事务。"""
import os
from pathlib import Path
import sys
import tempfile

from mdf_core.workspace.merge_policy import git


def push_release(repo, source, head, tag_ref, expected_remote):
    branch_ref = f"refs/heads/{source}"
    original = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-path", "hooks/pre-push").stdout.strip())
    original_hook = str(original) if original.is_file() and os.access(original, os.X_OK) else None
    expected_old = expected_remote or "0" * len(head)
    with tempfile.TemporaryDirectory(prefix="mdf-publish-hooks-") as directory:
        hook = Path(directory) / "pre-push"
        hook.write_text(
            f"#!{sys.executable}\n"
            "import subprocess, sys\n"
            "data = sys.stdin.buffer.read()\n"
            "updates = [line.split() for line in data.decode().splitlines()]\n"
            f"expected = {[head, branch_ref, expected_old]!r}\n"
            "if not any(len(row) == 4 and row[1:] == expected for row in updates):\n"
            "    sys.stderr.write('release ref 未参与预期的原子更新；重新执行 sync-remote\\n')\n"
            "    sys.exit(1)\n"
            f"original = {original_hook!r}\n"
            "if original:\n"
            "    sys.exit(subprocess.run([original, *sys.argv[1:]], input=data).returncode)\n"
        )
        hook.chmod(0o700)
        git(repo, "-c", f"core.hooksPath={directory}", "push", "--atomic", "--no-follow-tags",
            f"--force-with-lease={branch_ref}:{expected_remote or ''}", "origin",
            f"{head}:{branch_ref}", f"{tag_ref}:{tag_ref}")
