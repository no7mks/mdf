"""解析 to 目标：别名、已有 worktree，或为已有分支建树。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import MDFError, emit
from .gitutil import (
    primary_worktree,
    repo_path,
    require_git_root,
    run,
    sibling_worktree,
    worktree_map,
)
from .planning import ensure_planning


PLANNING_ALIASES = frozenset({"plan", "planning", "plan-mode"})
DEVELOP_ALIASES = frozenset({"develop"})


def _normalize(target: str) -> str:
    return target.strip().lower().replace("_", "-").replace(" ", "-")


def _exists(repo: Path, ref: str) -> bool:
    return not run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=repo,
        check=False,
    ).returncode


def command_to(args: Any) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    raw = (args.target or "").strip()
    if not raw:
        raise MDFError(
            "to 需要目标", code="bad_target", details=_available(repo),
        )
    emit(_resolve(repo, raw))


def _resolve(repo: Path, raw: str) -> dict[str, Any]:
    key = _normalize(raw)
    primary = primary_worktree(repo)
    trees = worktree_map(primary)
    if key in PLANNING_ALIASES:
        result = ensure_planning(repo)
        return _payload(raw, "planning", result["branch"],
                        Path(result["worktree"]), result["created"])
    if key in DEVELOP_ALIASES:
        path = trees.get("develop")
        if path is None:
            raise MDFError(
                "没有占用 develop 的 worktree",
                code="develop_unoccupied",
                details=_available(repo),
            )
        return _payload(raw, "develop", "develop", path, False)
    matches = _match_worktrees(trees, raw, key)
    paths = {path.resolve() for _, path in matches}
    if len(paths) == 1:
        branch, path = next(
            item for item in matches if item[1].resolve() in paths
        )
        return _payload(raw, None, branch, path, False)
    if len(paths) > 1:
        raise MDFError(
            "目标匹配多棵 worktree",
            code="ambiguous_target",
            details=_available(repo),
        )
    branch = _existing_branch(repo, raw)
    if branch is None:
        raise MDFError(
            "未知目标", code="unknown_target", details=_available(repo),
        )
    occupant = trees.get(branch)
    if occupant is not None:
        return _payload(raw, None, branch, occupant, False)
    path = sibling_worktree(repo, branch)
    if path.exists():
        raise MDFError("并行分支或 worktree 已存在", code="collision")
    path.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "worktree", "add", str(path), branch], cwd=primary)
    return _payload(raw, None, branch, path, True)


def _payload(
    raw: str, alias: str | None, branch: str, path: Path, created: bool,
) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": "to",
        "target": raw,
        "alias": alias,
        "branch": branch,
        "worktree": str(path),
        "created": created,
    }


def _match_worktrees(
    trees: dict[str, Path], raw: str, key: str,
) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for branch, path in trees.items():
        names = {branch, branch.lower(), path.name, path.name.lower()}
        if raw in names or key in {branch.lower(), path.name.lower()}:
            found.append((branch, path))
    return found


def _existing_branch(repo: Path, raw: str) -> str | None:
    for candidate in (raw, _normalize(raw)):
        if candidate and _exists(repo, f"refs/heads/{candidate}"):
            return candidate
    return None


def _available(repo: Path) -> dict[str, Any]:
    trees = worktree_map(primary_worktree(repo))
    return {
        "aliases": {
            "planning": sorted(PLANNING_ALIASES),
            "develop": sorted(DEVELOP_ALIASES),
        },
        "worktrees": {branch: str(path) for branch, path in trees.items()},
    }
