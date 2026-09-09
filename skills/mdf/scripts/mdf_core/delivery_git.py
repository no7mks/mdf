"""用户选择并行时的本地角色分支和集成。"""
from pathlib import Path

from .delivery_state import gate, git, matches, require_design
from .errors import MDFError
from .gitutil import current_branch, ensure_clean


def parallel(repo, root, data):
    ensure_clean(repo)
    require_design(repo, root, data)
    if current_branch(repo) != data["branch"]:
        raise MDFError("仅 feature 可建立并行分支", code="stage_branch")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    result = []
    for role in ("qa", "dev"):
        branch = f"{role}/{data['slug']}"
        path = repo.parent / f"{repo.name}-{role}-{data['slug']}"
        if path.exists() or not git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode:
            raise MDFError("并行分支或 worktree 已存在", code="collision")
        result.append({"branch": branch, "path": str(path), "base": base})
    for item in result:
        git(repo, "worktree", "add", "-b", item["branch"], item["path"], base)
    return {"worktrees": result}


def integrate(repo, root, data, approval):
    ensure_clean(repo)
    current = require_design(repo, root, data)
    if current_branch(repo) != data["branch"]:
        raise MDFError("仅 feature 可集成", code="stage_branch")
    policy = gate(repo, root, "design")["policy"]
    available = []
    raw = git(repo, "worktree", "list", "--porcelain").stdout
    worktrees = {}
    for block in raw.strip().split("\n\n"):
        values = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        if "branch" in values:
            worktrees[values["branch"].removeprefix("refs/heads/")] = Path(values["worktree"])
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
