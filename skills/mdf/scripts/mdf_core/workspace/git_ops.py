"""Deterministic Git init and no-ff merge for skill workflows."""

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.workspace.gitutil import (
    current_branch,
    ensure_clean,
    forget_git_root,
    git_in_progress_head,
    git_root,
    repo_path,
    require_git_root,
    run,
)


def command_prepare_git(args) -> None:
    from mdf_core.workspace.gitutil import valid_branch_name
    from mdf_core.workspace.workflow_policy import DEFAULT_TRUNK
    trunk = getattr(args, "trunk", None) or DEFAULT_TRUNK
    if not valid_branch_name(trunk):
        raise MDFError(f"workflow.trunk 不是合法分支名：{trunk}", code="invalid_workflow")
    path = repo_path(args.repo)
    root = git_root(path)
    if root is not None and root != path:
        raise MDFError(
            f"位于其他仓库内部（{root}），不嵌套 git init",
            code="nested_git",
            details={"git_root": str(root)},
        )
    created = False
    if root is None:
        result = run(
            ["git", "init", f"--initial-branch={trunk}", "--template="],
            cwd=path,
            check=False,
        )
        if result.returncode:
            raise MDFError(
                result.stderr.strip() or "git init 失败",
                code="git_init_failed",
            )
        created = True
        forget_git_root(path)
    require_git_root(path)
    emit(
        {
            "ok": True,
            "operation": "prepare-git",
            "created": created,
            "git_root": str(path),
            "branch": current_branch(path),
        }
    )


def command_merge_no_ff(args) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    if current_branch(repo).startswith("pm/rework/"):
        from mdf_core.lifecycle.pull_finish import finish_lock
        from mdf_core.workspace.pm import rework_source

        with finish_lock(repo):
            if rework_source(repo, current_branch(repo)) is None:
                raise MDFError("需要已登记的 pm 临时 worktree", code="invalid_worktree")
            merge_no_ff(repo, args.commit)
        return
    merge_no_ff(repo, args.commit)


def merge_no_ff(repo, source):
    ensure_clean(repo)
    from mdf_core.workspace.merge_policy import require_merge
    require_merge(repo, source, current_branch(repo))
    verified = run(
        ["git", "rev-parse", "--verify", source],
        cwd=repo,
        check=False,
    )
    if verified.returncode:
        raise MDFError(f"无法解析合并目标 {source}", code="bad_commit")
    from mdf_core.lifecycle.late_decision import guard_catch_up
    guard_catch_up(repo, verified.stdout.strip())
    from mdf_core.workspace.squash import require_ready
    require_ready(repo)
    incoming = run(
        ["git", "for-each-ref", "--format=%(refname)",
         f"--points-at={verified.stdout.strip()}", "refs/heads"], cwd=repo,
    ).stdout.splitlines()
    for branch in incoming:
        require_ready(repo, branch.removeprefix("refs/heads/"))
    before = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    result = run(["git", "merge", "--no-ff", source], cwd=repo, check=False)
    if result.returncode:
        raise MDFError(
            "no-ff 合并冲突，保留现场",
            code="merge_conflict",
            details={"head": git_in_progress_head(repo)},
        )
    after = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    emit(
        {
            "ok": True,
            "operation": "merge-no-ff",
            "merged": before != after,
            "commit": after,
            "branch": current_branch(repo),
        }
    )
