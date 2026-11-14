"""github-flow + pr 的 release 集成分支：release_head 与 origin/<trunk> 冲突或需对齐时，由独立分支合并后再 PR。"""
from pathlib import Path
import re

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.lifecycle.delivery_state import read_json, write_json
from mdf_core.lifecycle.publish import state_path
from mdf_core.workspace.gitutil import (
    branch_details, current_branch, ensure_clean, git_in_progress_head, repo_path, require_git_root, sibling_worktree,
    worktree_map,
)
from mdf_core.workspace.merge_policy import ancestor, git, sha
from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch

PREFIX = "codex/integrate/release-"


def integration_version(source):
    """integration 分支名中的 semver；非 integration 分支返回 None。"""
    match = re.fullmatch(re.escape(PREFIX) + r"(\d+\.\d+\.\d+)", source or "")
    return match.group(1) if match else None


def record_path(repo, version):
    return state_path(repo, f"integrate/{version}")


def release_head_of(repo, source):
    """integration 分支绑定的固定 release_head；缺记录即不可发布。"""
    version = integration_version(source)
    path = record_path(repo, version)
    if not path.exists():
        raise MDFError("integration 分支缺少 release_head 记录", code="pull_state_changed")
    record = read_json(path)
    if not ancestor(repo, record["release_head"], f"refs/heads/{source}"):
        raise MDFError("integration 分支不再包含 release_head", code="release_head_unreachable")
    return record["release_head"]


def conflicts_with_trunk(repo, release_head, trunk):
    """release_head 与 origin/<trunk> 无法干净合并时返回 True；已含 trunk 或可 ff 视为无冲突。"""
    remote = f"refs/remotes/origin/{trunk}"
    if ancestor(repo, remote, release_head):
        return False
    return git(repo, "merge-tree", "--write-tree", "--no-messages", remote, release_head, check=False).returncode != 0


def require_direct_pr(repo, source):
    """release 源分支直接 PR 前核验；冲突时要求改走 integration 分支。"""
    if not (is_github_flow(repo) and branch_details(source)["kind"] == "release"):
        return
    trunk = trunk_branch(repo)
    if conflicts_with_trunk(repo, sha(repo, source), trunk):
        version = branch_details(source)["version"]
        raise MDFError(f"release/{version} 与 {trunk} 冲突；先执行 release-integrate 建立集成分支",
                       code="integration_required", details={"integration": f"{PREFIX}{version}"})


def command_release_integrate(args):
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_clean(repo)
    from mdf_core.workspace.merge_policy import configured
    source = args.source or current_branch(repo)
    details = branch_details(source)
    if not is_github_flow(repo) or configured(repo)["mode"] != "pr" or details["kind"] != "release":
        raise MDFError("release-integrate 仅用于 github-flow + pr 的 release 分支", code="invalid_closeout")
    version, trunk = details["version"], trunk_branch(repo)
    branch = f"{PREFIX}{version}"
    path = record_path(repo, version)
    git(repo, "fetch", "origin", "--prune")
    remote = f"refs/remotes/origin/{trunk}"
    record = read_json(path) if path.exists() else None
    current = sha(repo, source)
    if record is None:
        record = {"release": source, "version": version, "release_head": current, "branch": branch}
        write_json(path, record)
    elif record.get("release_head") != current:
        if not ancestor(repo, record["release_head"], f"refs/heads/{source}"):
            raise MDFError("release 源分支已偏离已固定的 release_head", code="pull_state_changed")
        opened = state_path(repo, branch)
        if opened.exists() and read_json(opened).get("pull"):
            raise MDFError("PR 已创建后 release_head 变化", code="release_head_changed",
                           details={"release_head": record["release_head"], "head": current})
        record["release_head"] = current
        write_json(path, record)
    work = worktree_map(repo).get(branch)
    if work is None:
        work = sibling_worktree(repo, branch)
        if work.exists():
            raise MDFError("integration worktree 路径已存在", code="collision")
        work.parent.mkdir(parents=True, exist_ok=True)
        exists = git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0
        if exists:
            git(repo, "worktree", "add", str(work), branch)
        else:
            git(repo, "worktree", "add", "-b", branch, str(work), record["release_head"])
    if git_in_progress_head(work):
        raise MDFError("integration 分支有未完成的 merge；解决并提交后重试", code="unfinished_merge",
                       details={"worktree": str(work)})
    ensure_clean(work)
    status = "up_to_date"
    if not ancestor(work, record["release_head"], "HEAD"):
        result = git(work, "merge", "--no-ff", "--no-commit", record["release_head"], check=False)
        if result.returncode:
            conflicts = git(work, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
            raise MDFError("integration merge 冲突；在 worktree 解决后提交，再执行 $mdf pr",
                           code="merge_conflict", details={"worktree": str(work), "conflicts": conflicts})
        if git_in_progress_head(work):
            git(work, "commit", "-m", f"chore(release): 纳入新的 release_head 到 release/{version}")
        status = "merged"
    if not ancestor(work, remote, "HEAD"):
        result = git(work, "merge", "--no-ff", "--no-commit", remote, check=False)
        if result.returncode:
            conflicts = git(work, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
            raise MDFError("integration merge 冲突；在 worktree 解决后提交，再执行 $mdf pr",
                           code="merge_conflict", details={"worktree": str(work), "conflicts": conflicts})
        if git_in_progress_head(work):
            git(work, "commit", "-m", f"chore(release): 集成 {trunk} 到 release/{version}")
        status = "merged"
    emit({"ok": True, "operation": "release-integrate", "branch": branch, "worktree": str(Path(work)),
          "release_head": record["release_head"], "status": status, "next_intent": "pr"})
