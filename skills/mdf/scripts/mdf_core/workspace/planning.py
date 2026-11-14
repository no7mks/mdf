"""gitflow 的常驻 planning 分支与 sibling worktree。"""

from __future__ import annotations

from pathlib import Path

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.workspace.gitutil import (
    current_branch,
    ensure_clean,
    git_in_progress_head,
    git_is_clean,
    primary_worktree,
    repo_path,
    require_git_root,
    run,
    sibling_worktree,
    worktree_map,
)


BRANCH = "planning"


def _git(repo: Path, *args: str, check: bool = True):
    return run(["git", *args], cwd=repo, check=check)


def _exists(repo: Path, ref: str) -> bool:
    return not _git(repo, "rev-parse", "--verify", "--quiet", ref,
                    check=False).returncode


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    return _git(
        repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False,
    ).returncode == 0


def merge_branch(repo: Path, source: str) -> bool:
    """master、develop 与 planning：能 fast-forward 则 ff，已分叉则 no-ff。"""
    if git_in_progress_head(repo) == "MERGE_HEAD":
        raise MDFError(
            "未结束的合并（MERGE_HEAD 仍在）；"
            "先完成提交或执行 git merge --abort",
            code="unfinished_merge",
        )
    if _is_ancestor(repo, source, "HEAD"):
        return False
    from mdf_core.workspace.merge_policy import require_merge
    require_merge(repo, source, current_branch(repo))
    if _is_ancestor(repo, "HEAD", source):
        _git(repo, "merge", "--ff-only", source)
        return True
    result = _git(repo, "merge", "--no-ff", "--no-commit", source, check=False)
    if result.returncode:
        if (
            result.returncode != 1
            and git_in_progress_head(repo) == "MERGE_HEAD"
        ):
            raise MDFError(
                "未结束的合并（MERGE_HEAD 仍在）；"
                "先完成提交或执行 git merge --abort",
                code="unfinished_merge",
            )
        _git(repo, "merge", "--abort", check=False)
        raise MDFError(
            f"Merge conflict: {source} -> {current_branch(repo)}; "
            "merge was aborted",
            code="merge_conflict",
        )
    # 分叉历史即使 tree 相同，也必须提交 merge，才能把规划与主线真正对齐。
    if git_in_progress_head(repo) != "MERGE_HEAD":
        return False
    target = current_branch(repo)
    _git(repo, "commit", "-m",
         f"chore(planning): 合并 {source} 到 {target}")
    return True


def command_planning(args) -> None:
    if args.action == "ensure":
        command_planning_ensure(args)
        return
    command_planning_land(args)


def command_planning_ensure(args) -> None:
    emit(ensure_planning(repo_path(args.repo)))


def ensure_planning(repo: Path) -> dict:
    require_git_root(repo)
    from mdf_core.workspace.workflow_policy import require_gitflow, trunk_branch
    require_gitflow(repo, "planning ensure")
    trunk = trunk_branch(repo)
    if not _exists(repo, f"refs/heads/{trunk}"):
        raise MDFError(f"Branch {trunk} must exist", code="missing_branch")
    primary = primary_worktree(repo)
    path = sibling_worktree(repo, BRANCH)
    trees = worktree_map(primary)
    occupant = trees.get(BRANCH)
    created = False
    if occupant is not None:
        if occupant.resolve() != path.resolve():
            raise MDFError(
                "planning 已被其他 worktree 占用",
                code="planning_occupied",
            )
        work = occupant
    else:
        if path.exists():
            raise MDFError("并行分支或 worktree 已存在", code="collision")
        path.parent.mkdir(parents=True, exist_ok=True)
        if _exists(repo, f"refs/heads/{BRANCH}"):
            _git(primary, "worktree", "add", str(path), BRANCH)
        else:
            _git(primary, "worktree", "add", "-b", BRANCH, str(path), trunk)
        created = True
        work = path
    synced = False
    if git_is_clean(work):
        merge_branch(work, trunk)
        synced = True
    return {
        "ok": True,
        "operation": "planning-ensure",
        "branch": BRANCH,
        "worktree": str(work),
        "created": created,
        "synced": synced,
    }


def command_planning_land(args) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    from mdf_core.workspace.workflow_policy import require_gitflow, trunk_branch
    require_gitflow(repo, "planning land")
    if not _exists(repo, f"refs/heads/{BRANCH}"):
        raise MDFError("Branch planning must exist", code="missing_branch")
    trunk = trunk_branch(repo)
    primary = primary_worktree(repo)
    trees = worktree_map(primary)
    planning_wt = trees.get(BRANCH)
    # 在任何写入前检查全部已占用目标，避免 land 后才发现脏 develop。
    for branch in (BRANCH, trunk, "develop"):
        if not _exists(repo, f"refs/heads/{branch}"):
            raise MDFError(f"Branch {branch} must exist", code="missing_branch")
        if branch in trees:
            ensure_clean(trees[branch])
    from mdf_core.workspace.squash import require_ready
    require_ready(planning_wt or primary, BRANCH)

    def checkout(branch):
        if branch in trees:
            return trees[branch]
        path = sibling_worktree(repo, branch)
        if path.exists():
            raise MDFError("目标 worktree 路径已存在", code="collision")
        path.parent.mkdir(parents=True, exist_ok=True)
        _git(primary, "worktree", "add", str(path), branch)
        trees[branch] = path
        return path

    trunk_wt, develop = checkout(trunk), checkout("develop")
    landed = merge_branch(trunk_wt, BRANCH)
    backmerged = merge_branch(develop, trunk)
    synced = False
    if planning_wt is not None:
        merge_branch(planning_wt, trunk)
        synced = True
    emit({
        "ok": True,
        "operation": "planning-land",
        "landed": landed,
        "backmerged": backmerged,
        "synced": synced,
    })
