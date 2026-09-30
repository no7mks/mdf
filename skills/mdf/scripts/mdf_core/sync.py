"""三大 trunk（master / develop / planning）与 origin 对齐：先拉后推。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import MDFError, emit
from .gitutil import (
    current_branch,
    ensure_clean,
    git_in_progress_head,
    primary_worktree,
    repo_path,
    require_git_root,
    run,
    worktree_map,
)

ORIGIN = "origin"
TRUNKS = ("master", "develop", "planning")


def _git(repo: Path, *args: str, check: bool = True):
    return run(["git", *args], cwd=repo, check=check)


def _exists(repo: Path, ref: str) -> bool:
    return not _git(
        repo, "rev-parse", "--verify", "--quiet", ref, check=False
    ).returncode


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    return _git(
        repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False,
    ).returncode == 0


def _sha(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", ref).stdout.strip()


def _require_origin(repo: Path) -> None:
    if _git(repo, "remote", "get-url", ORIGIN, check=False).returncode:
        raise MDFError("sync 需要 remote origin", code="missing_origin")


def _local_heads(repo: Path) -> list[str]:
    raw = _git(
        repo, "for-each-ref", "--format=%(refname:short)", "refs/heads",
    ).stdout
    return [line for line in raw.splitlines() if line]


def _remote_heads(repo: Path) -> list[str]:
    raw = _git(
        repo, "for-each-ref", "--format=%(refname:short)",
        f"refs/remotes/{ORIGIN}",
    ).stdout
    names: list[str] = []
    for line in raw.splitlines():
        name = line.removeprefix(f"{ORIGIN}/")
        if name and name != "HEAD":
            names.append(name)
    return names


def _pull_into(work: Path, branch: str) -> str:
    """把 origin/<branch> 合入当前 checkout；返回 noop / ff / merged。"""
    remote = f"{ORIGIN}/{branch}"
    if git_in_progress_head(work) == "MERGE_HEAD":
        raise MDFError(
            "未结束的合并（MERGE_HEAD 仍在）；"
            "先完成提交或执行 git merge --abort",
            code="unfinished_merge",
        )
    if current_branch(work) != branch:
        _git(work, "checkout", branch)
    if _is_ancestor(work, remote, "HEAD"):
        return "noop"
    if _is_ancestor(work, "HEAD", remote):
        _git(work, "merge", "--ff-only", remote)
        return "ff"
    result = _git(
        work, "merge", "--no-ff", "--no-commit", remote, check=False,
    )
    if result.returncode:
        if (
            result.returncode != 1
            and git_in_progress_head(work) == "MERGE_HEAD"
        ):
            raise MDFError(
                "未结束的合并（MERGE_HEAD 仍在）；"
                "先完成提交或执行 git merge --abort",
                code="unfinished_merge",
            )
        _git(work, "merge", "--abort", check=False)
        raise MDFError(
            f"Merge conflict: {remote} -> {branch}; merge was aborted",
            code="merge_conflict",
        )
    if not _git(work, "status", "--porcelain").stdout.strip():
        if git_in_progress_head(work) == "MERGE_HEAD":
            _git(work, "merge", "--abort", check=False)
        return "noop"
    _git(
        work, "commit", "-m",
        f"chore(sync): 合并 {remote} 到 {branch}",
    )
    return "merged"


def command_sync(args) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    _require_origin(repo)
    primary = primary_worktree(repo)
    _git(primary, "fetch", ORIGIN, "--prune")

    for branch in TRUNKS:
        local = f"refs/heads/{branch}"
        remote = f"refs/remotes/{ORIGIN}/{branch}"
        if not _exists(primary, local) or not _exists(primary, remote):
            raise MDFError(
                f"Branch {branch} and {ORIGIN}/{branch} must both exist",
                code="missing_upstream_branch",
            )

    trees = worktree_map(primary)
    need_primary = False
    for branch in TRUNKS:
        occupant = trees.get(branch)
        if occupant is not None:
            ensure_clean(occupant)
        else:
            need_primary = True
    if need_primary:
        ensure_clean(primary)

    extras_local = sorted(name for name in _local_heads(primary)
                          if name not in TRUNKS)
    extras_remote = sorted(name for name in _remote_heads(primary)
                           if name not in TRUNKS)

    original = current_branch(primary) if need_primary else None
    trunks: dict[str, Any] = {}
    try:
        for branch in TRUNKS:
            work = trees.get(branch) or primary
            before_remote = _sha(primary, f"{ORIGIN}/{branch}")
            before_local = _sha(primary, branch)
            pull = _pull_into(work, branch)
            after_local = _sha(primary, branch)
            trunks[branch] = {
                "pull": pull,
                "before": before_local,
                "after": after_local,
                "origin_before": before_remote,
                "worktree": str(work),
            }
    finally:
        if original is not None and current_branch(primary) != original:
            _git(primary, "checkout", original)

    _git(primary, "push", "--atomic", ORIGIN, *TRUNKS)
    for branch, info in trunks.items():
        info["push"] = (
            "noop" if info["after"] == info["origin_before"] else "updated"
        )

    emit({
        "ok": True,
        "operation": "sync",
        "trunks": trunks,
        "extra_local": extras_local,
        "extra_remote": extras_remote,
    })
