"""角色分支集成。"""
import json

from .delivery_state import gate, git, matches, require_design, role_names, read_json, safe, write_json
from .errors import MDFError
from .gitutil import current_branch, ensure_clean, worktree_map


def integrate(repo, root, data, approval):
    ensure_clean(repo)
    current = require_design(repo, root, data)
    if current_branch(repo) != data["branch"]:
        raise MDFError("仅 feature 可集成", code="stage_branch")
    policy = gate(repo, root, "design")["policy"]
    receipt_path = safe(repo, root / "gates/integration.json")
    receipt = read_json(receipt_path) if receipt_path.exists() else None
    expected_names = set(role_names(data["branch"]).values())
    if receipt is not None:
        if (receipt.get("design") != current["design"]
                or set(receipt.get("branches", {})) != expected_names):
            raise MDFError("集成记录与当前交付不一致", code="stale_integration")
        for branch, head in receipt["branches"].items():
            if git(repo, "merge-base", "--is-ancestor", head, "HEAD", check=False).returncode:
                raise MDFError("集成提交不在 owner 历史中", code="stale_integration")
            ref = git(repo, "rev-parse", "--verify", f"refs/heads/{branch}", check=False)
            if not ref.returncode and ref.stdout.strip() != head:
                raise MDFError("角色分支在集成后变化", code="stale_integration")
        return cleanup(repo, receipt["branches"])
    available = []
    worktrees = worktree_map(repo)
    for role, stage in (("qa", "write-tests"), ("dev", "implement")):
        branch = role_names(data["branch"])[role]
        if git(repo, "show-ref", "--verify", f"refs/heads/{branch}",
               check=False).returncode:
            raise MDFError(f"缺少角色分支 {branch}", code="missing_role")
        if branch in worktrees:
            ensure_clean(worktrees[branch])
        rel = str((root / "gates" / f"{stage}.json").relative_to(repo))
        shown = git(repo, "show", f"{branch}:{rel}", check=False)
        if shown.returncode:
            raise MDFError(f"角色分支缺少 {stage} 记录", code="stale_gate")
        try:
            record = json.loads(shown.stdout)
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
        if not git(repo, "merge-base", "--is-ancestor", branch, "HEAD",
                    check=False).returncode:
            continue
        result = git(repo, "merge", "--no-ff", "--no-commit", branch, check=False)
        if result.returncode:
            # Preserve conflicts for contract-based review; no silent test resolution.
            raise MDFError("集成冲突，保留现场；涉及测试的解决需用户确认",
                           code="merge_conflict")
        git(repo, "commit", "-m", f"chore(delivery): 集成 {branch}")
    receipt = {"design": current["design"], "branches": {
        branch: git(repo, "rev-parse", f"refs/heads/{branch}").stdout.strip() for branch in available}}
    write_json(receipt_path, receipt)
    git(repo, "add", "--", str(receipt_path.relative_to(repo)))
    git(repo, "commit", "-m", "chore(delivery): 固定角色集成证据")
    return cleanup(repo, receipt["branches"])


def cleanup(repo, branches):
    worktrees = worktree_map(repo)
    for branch in branches:
        if branch in worktrees:
            ensure_clean(worktrees[branch])
            git(repo, "worktree", "remove", str(worktrees[branch]))
        if not git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode:
            git(repo, "branch", "-d", branch)
    return {"integrated": list(branches)}
