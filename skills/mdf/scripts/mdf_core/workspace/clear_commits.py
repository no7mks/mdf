"""同一 Git clone 的四个通过节点，各自按两端内容比较。"""
import fcntl
import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from mdf_core.workspace.gitutil import git_is_clean
from mdf_core.reviewing.worktree import git, sha

KEYS = ("verify_smoke", "verify_release", "code_review", "fact_audit")


def state_file(repo):
    common = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    return Path(common) / "mdf" / "clear-commits.json"


def _read(path):
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def load(repo, key):
    value = _read(state_file(repo)).get(key)
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value):
        return None
    found = git(repo, "rev-parse", "--verify", "--quiet", f"{value}^{{commit}}", check=False)
    return value if not found.returncode and found.stdout.strip() == value else None


def changed_paths(repo, left, right=None, *, dirty=False):
    args = ("--no-renames", "--name-only", "--ignore-submodules=none", "-z")
    if not dirty:
        return set(git(repo, "diff", *args, left, right or "HEAD", "--").stdout.split("\0")) - {""}
    staged = git(repo, "diff", "--cached", *args, left, "--").stdout
    unstaged = git(repo, "diff", *args, "--").stdout
    untracked = git(repo, "ls-files", "--others", "--exclude-standard", "-z").stdout
    return set((staged + unstaged + untracked).split("\0")) - {""}


def record(repo, key, head, *, expected):
    return _update(repo, key, head, head, expected)


def invalidate(repo, key, head, *, expected):
    return _update(repo, key, head, None, expected)


def _update(repo, key, head, value, expected):
    """只更新同一个 clean HEAD 的记录，保留并行写入的同类结果。"""
    if not git_is_clean(repo):
        return False
    path = state_file(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = os.open(path.parent, os.O_RDONLY)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if sha(repo, "HEAD") != head or not git_is_clean(repo) or load(repo, key) != expected:
            return False
        state = _read(path)
        state = {name: state[name] for name in KEYS if name in state}
        if value is None:
            state.pop(key, None)
        else:
            state[key] = value
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temp:
            temporary = Path(temp.name)
            try:
                temp.write(json.dumps(state, indent=2) + "\n")
                temp.close()
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
    finally:
        os.close(lock)
    return True
