"""强制角色 worktree 与集成。"""
from .delivery_state import gate, git, matches, require_design
from .errors import MDFError
from .gitutil import (
    add_linked_worktree,
    current_branch,
    ensure_clean,
    sibling_worktree,
    worktree_map,
)


def add_role(repo, root, data, role):
    if role not in ("qa", "dev"):
        raise MDFError("角色必须是 qa 或 dev", code="invalid_role")
    ensure_clean(repo)
    require_design(repo, root, data)
    branch = f"{role}/{data['slug']}"
    path = sibling_worktree(repo, f"{role}-{data['slug']}")
    rel = str((root / "gates" / "design.json").relative_to(repo))
    base = git(repo, "log", "-1", "--format=%H", "--", rel).stdout.strip()
    if len(base) < 40 or any(c not in "0123456789abcdef" for c in base):
        raise MDFError("缺少已提交的设计基线", code="stale_gate")
    worktrees = worktree_map(repo)
    if branch in worktrees:
        return {"worktree": {"branch": branch, "path": str(worktrees[branch]),
                             "base": base}}
    exists = git(repo, "show-ref", "--verify", f"refs/heads/{branch}",
                 check=False)
    if path.exists():
        raise MDFError("并行分支或 worktree 已存在", code="collision")
    if not exists.returncode:
        git(repo, "worktree", "add", str(path), branch)
    else:
        add_linked_worktree(repo, branch, path, base)
    return {"worktree": {"branch": branch, "path": str(path), "base": base}}


def integrate(repo, root, data, approval):
    ensure_clean(repo)
    current = require_design(repo, root, data)
    if current_branch(repo) != data["branch"]:
        raise MDFError("仅 feature 可集成", code="stage_branch")
    policy = gate(repo, root, "design")["policy"]
    available = []
    worktrees = worktree_map(repo)
    for role, stage in (("qa", "write-tests"), ("dev", "implement")):
        branch = f"{role}/{data['slug']}"
        if git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode:
            continue
        if branch in worktrees:
            ensure_clean(worktrees[branch])
        rel = str((root / "gates" / f"{stage}.json").relative_to(repo))
        import json
        try:
            record = json.loads(git(repo, "show", f"{branch}:{rel}").stdout)
        except ValueError as exc:
            raise MDFError("角色分支阶段记录损坏", code="invalid_delivery") from exc
        if record.get("fingerprints", {}).get("design") != current["design"]:
            raise MDFError("角色分支没有共同设计基线", code="stale_gate")
        common = git(repo, "merge-base", "HEAD", branch).stdout.strip()
        changed = git(repo, "diff", "--name-only", common, branch).stdout.splitlines()
        protected = [name for name in changed if matches(name, policy["protected_paths"])
                     or name == ".mdf/manifest.yaml"]
        if role == "dev" and protected and not approval:
            raise MDFError("实现分支修改了测试或验证规则", code="test_approval_required",
                           details={"paths": protected})
        available.append(branch)
    for branch in available:
        if not git(repo, "merge-base", "--is-ancestor", branch, "HEAD", check=False).returncode:
            continue
        result = git(repo, "merge", "--no-ff", "--no-commit", branch, check=False)
        if result.returncode:
            # Preserve conflicts for contract-based review; no silent test resolution.
            raise MDFError("集成冲突，保留现场；涉及测试的解决需用户确认", code="merge_conflict")
        git(repo, "commit", "-m", f"chore(delivery): 集成 {branch}")
    for branch in available:
        if branch in worktrees:
            git(repo, "worktree", "remove", str(worktrees[branch]))
        git(repo, "branch", "-d", branch)
    return {"integrated": available}
