"""角色分支集成。"""
import json

from .delivery_state import (
    fingerprints, gate, git, matches, require_design, read_json, safe, write_json,
)
from .errors import MDFError
from .gitutil import current_branch, ensure_clean, worktree_map
from .roster import merge_branches, role_branches


def integrate(repo, root, data, approval, qa_branch=None, dev_branch=None):
    ensure_clean(repo)
    current = require_design(repo, root, data)
    if current_branch(repo) != data["branch"]:
        raise MDFError("仅 owner 可集成", code="stage_branch")
    policy = gate(repo, root, "design")["policy"]
    receipt_path = safe(repo, root / "gates/integration.json")
    receipt = read_json(receipt_path) if receipt_path.exists() else None
    expected_names = role_branches(data["branch"], data["roster"])
    qa_merged = merge_branches(
        "qa", data["branch"], data["roster"], qa_branch,
    )
    dev_merged = merge_branches(
        "dev", data["branch"], data["roster"], dev_branch,
    )
    merged = [*qa_merged, *dev_merged]
    if receipt is not None:
        if (receipt.get("design") != current["design"]
                or set(receipt.get("branches", {})) != set(expected_names)
                or set(receipt.get("merged", [])) != set(merged)):
            raise MDFError("集成记录与当前交付不一致", code="stale_integration")
        for branch, head in receipt["branches"].items():
            if branch in receipt.get("merged", []):
                if git(repo, "merge-base", "--is-ancestor", head, "HEAD",
                       check=False).returncode:
                    raise MDFError("集成提交不在 owner 历史中",
                                   code="stale_integration")
            ref = git(repo, "rev-parse", "--verify", f"refs/heads/{branch}",
                      check=False)
            if not ref.returncode and ref.stdout.strip() != head:
                raise MDFError("角色分支在集成后变化", code="stale_integration")
        return cleanup(repo, expected_names)
    worktrees = worktree_map(repo)
    for branch in expected_names:
        if git(repo, "show-ref", "--verify", f"refs/heads/{branch}",
               check=False).returncode:
            raise MDFError(f"缺少角色分支 {branch}", code="missing_role")
        if branch in worktrees:
            ensure_clean(worktrees[branch])
    for branch, stage, role in (
        *((name, "write-tests", "qa") for name in qa_merged),
        *((name, "implement", "dev") for name in dev_merged),
    ):
        rel = str((root / "gates" / f"{stage}.json").relative_to(repo))
        shown = git(repo, "show", f"{branch}:{rel}", check=False)
        if shown.returncode:
            raise MDFError(f"角色分支缺少 {stage} 记录", code="stale_gate")
        try:
            record = json.loads(shown.stdout)
        except ValueError as exc:
            raise MDFError("角色分支阶段记录损坏",
                           code="invalid_delivery") from exc
        if record.get("fingerprints", {}).get("design") != current["design"]:
            raise MDFError("角色分支没有共同设计基线", code="stale_gate")
        common = git(repo, "merge-base", "HEAD", branch).stdout.strip()
        changed = git(repo, "diff", "--name-only", common, branch).stdout.splitlines()
        protected = [name for name in changed
                     if matches(name, policy["protected_paths"])
                     or name == ".mdf/manifest.yaml"]
        if role == "dev" and protected and not approval:
            raise MDFError("实现分支修改了测试或验证规则",
                           code="test_approval_required",
                           details={"paths": protected})
    for branch in qa_merged:
        merge_role(repo, root, branch)
    # 多路 qa 的 write-tests 记录冲突时只保留第一路；converge 以合并后的测试为基线。
    tests = fingerprints(repo, root, data)["tests"]
    for branch in dev_merged:
        merge_role(repo, root, branch)
    receipt = {
        "design": current["design"],
        "tests": tests,
        "merged": merged,
        "branches": {
            branch: git(repo, "rev-parse", f"refs/heads/{branch}").stdout.strip()
            for branch in expected_names
        },
    }
    write_json(receipt_path, receipt)
    git(repo, "add", "--", str(receipt_path.relative_to(repo)))
    git(repo, "commit", "-m", "chore(delivery): 固定角色集成证据")
    return cleanup(repo, expected_names)


def merge_role(repo, root, branch):
    if not git(repo, "merge-base", "--is-ancestor", branch, "HEAD",
                check=False).returncode:
        return
    result = git(repo, "merge", "--no-ff", "--no-commit", branch, check=False)
    if result.returncode:
        unmerged = git(repo, "diff", "--name-only", "--diff-filter=U"
                       ).stdout.splitlines()
        allowed = {
            str((root / "gates" / name).relative_to(repo))
            for name in ("write-tests.json", "implement.json")
        }
        if not unmerged or set(unmerged) - allowed:
            raise MDFError("集成冲突，保留现场；涉及测试的解决需用户确认",
                           code="merge_conflict")
        for path in unmerged:
            git(repo, "checkout", "--ours", "--", path)
            git(repo, "add", "--", path)
    git(repo, "commit", "-m", f"chore(delivery): 集成 {branch}")


def cleanup(repo, branches):
    worktrees = worktree_map(repo)
    for branch in branches:
        if branch in worktrees:
            ensure_clean(worktrees[branch])
            git(repo, "worktree", "remove", str(worktrees[branch]))
        if not git(repo, "show-ref", "--verify", f"refs/heads/{branch}",
                   check=False).returncode:
            git(repo, "branch", "-D", branch)
    return {"integrated": list(branches)}
