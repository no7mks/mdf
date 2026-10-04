"""manifest hook 配置与 start 成功后的执行。"""

import os
from pathlib import Path
import sys

from .errors import MDFError
from .paths import load_manifest, path_stays_in_repo
from .run_logs import stream_child


HOOK_NAME = "post-gitflow-start"


def validate_hooks(manifest):
    hooks = manifest.get("hooks", {})
    if not isinstance(hooks, dict):
        raise MDFError("hooks 必须为 mapping", code="invalid_hooks")
    for name, entry in hooks.items():
        if name != HOOK_NAME:
            raise MDFError(f"未知 hook：{name}", code="invalid_hooks")
        if not isinstance(entry, dict) or set(entry) != {"type", "path"}:
            raise MDFError("hook 必须只含 type 与 path", code="invalid_hooks")
        if entry["type"] not in ("command", "rule"):
            raise MDFError("hook type 必须为 command 或 rule", code="invalid_hooks")
        raw = entry["path"]
        if (not isinstance(raw, str) or not raw.strip()
                or Path(raw).is_absolute() or ".." in Path(raw).parts):
            raise MDFError("hook path 必须为 repo root 相对路径", code="invalid_hooks")
    return hooks


def post_gitflow_start(old_worktree, new_worktree):
    try:
        entry = validate_hooks(load_manifest(new_worktree)).get(HOOK_NAME)
        if entry is None:
            return None
        print(f"开始执行 hook {HOOK_NAME}：{entry['path']}；cwd={new_worktree}",
              file=sys.stderr, flush=True)
        path = new_worktree / entry["path"]
        if not path_stays_in_repo(new_worktree, path) or not path.is_file():
            raise MDFError("hook path 必须指向新 worktree 内的文件", code="invalid_hooks")
        result = {
            "name": HOOK_NAME, **entry, "cwd": str(new_worktree),
            "old_worktree": str(old_worktree), "new_worktree": str(new_worktree),
        }
        if entry["type"] == "rule":
            return {**result, "status": "pending"}
        try:
            returncode = stream_child(
                [str(path.resolve())], cwd=new_worktree,
                env={**os.environ, "MDF_OLD_WORKTREE": str(old_worktree),
                     "MDF_NEW_WORKTREE": str(new_worktree)},
            )
            result.update(status="success" if returncode == 0 else "failed",
                          returncode=returncode)
        except OSError as exc:
            result.update(status="failed", error=str(exc))
        print(f"hook {HOOK_NAME} 执行结束：{result['status']}；"
              "失败仅汇报，不影响 start", file=sys.stderr, flush=True)
        return result
    except MDFError as exc:
        print(f"hook {HOOK_NAME} 执行结束：失败：{exc}；不影响 start", file=sys.stderr, flush=True)
        return {"name": HOOK_NAME, "status": "failed", "error": str(exc)}
