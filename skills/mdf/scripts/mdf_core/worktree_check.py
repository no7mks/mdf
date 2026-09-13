"""核验分派目录、角色分支、共同 Git 仓库与交接证据；不写入。"""
from pathlib import Path

from .delivery_state import git, locate, require_design, role_names, gate
from .errors import MDFError, emit
from .gitutil import branch_details, current_branch, ensure_clean, repo_path, require_git_root, worktree_map


def common_dir(repo):
    return Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()).resolve()


def command_worktree_check(args):
    repo, owner = repo_path(args.repo), repo_path(args.owner)
    require_git_root(repo)
    require_git_root(owner)
    owner_branch = current_branch(owner)
    if not branch_details(owner_branch)["supported"] or (args.role != "owner"
                                                         and not owner_branch.startswith("feature/")):
        raise MDFError("角色与 owner 交付类型不符", code="stage_branch")
    expected = owner_branch if args.role == "owner" else role_names(owner_branch)[args.role]
    trees = worktree_map(owner)
    if (current_branch(repo) != expected or trees.get(expected, Path()).resolve() != repo
            or common_dir(repo) != common_dir(owner)
            or (args.role != "owner" and repo == owner)):
        raise MDFError("worktree 身份或仓库不匹配", code="wrong_worktree")
    if args.expected_head and git(repo, "rev-parse", "HEAD").stdout.strip() != args.expected_head:
        raise MDFError("审查 HEAD 已变化", code="stale_head")
    result = {"path": str(repo), "branch": expected, "common_dir": str(common_dir(repo))}
    if args.design_commit:
        if git(repo, "merge-base", "--is-ancestor", args.design_commit, "HEAD", check=False).returncode:
            raise MDFError("角色未包含共同设计提交", code="missing_design_commit")
        root, data = locate(repo)
        owner_root, owner_data = locate(owner)
        current = require_design(repo, root, data)
        if current["design"] != require_design(owner, owner_root, owner_data)["design"]:
            raise MDFError("角色与 owner 的设计不同", code="stale_gate")
        result["fingerprints"] = current
        if args.handoff:
            ensure_clean(repo)
            stage = {"qa": "write-tests", "dev": "implement"}.get(args.role)
            if stage is None:
                raise MDFError("交接只适用于 qa/dev", code="stage_branch")
            record = gate(repo, root, stage)
            key = "tests" if args.role == "qa" else "implementation"
            if any(record.get("fingerprints", {}).get(k) != current[k] for k in ("design", key)):
                raise MDFError("交接 gate 已过期", code="stale_gate")
            git(repo, "ls-files", "--error-unmatch", str((root / f"gates/{stage}.json").relative_to(repo)))
            result["head"] = git(repo, "rev-parse", "HEAD").stdout.strip()
    elif args.handoff:
        raise MDFError("交接需要固定设计提交", code="missing_design_commit")
    emit({"ok": True, "operation": "worktree-check", "result": result})
