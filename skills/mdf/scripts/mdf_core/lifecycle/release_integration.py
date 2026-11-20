"""github-flow + pr 的 release 集成分支：release_head 与 origin/<trunk> 冲突或需对齐时，由独立分支合并后再 PR。"""
import re

from mdf_core.foundation.errors import MDFError, emit
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


def release_head_of(repo, source, *, ref=None):
    """从已提交的集成历史读取发布 SHA，并核对父节点和交付身份。"""
    ref = ref or f"refs/heads/{source}"
    version = integration_version(source)
    source = f"release/{version}"
    rows = git(repo, "log", "--first-parent", "--format=%P%x09%(trailers:key=MDF-Release-Head,valueonly,separator=%x2C)",
               ref).stdout.splitlines()
    for row in rows:
        parents, _, release = row.partition("\t")
        if not release:
            continue
        parents = parents.split()
        if re.fullmatch(r"[0-9a-f]{40}", release) is None or not parents or release != parents[-1] or len(parents) > 2:
            raise MDFError("发布 SHA 与集成提交父节点不符", code="release_head_unreachable")
        from mdf_core.lifecycle.late_decision import identity_at
        published = git(repo, "cat-file", "-e", f"{release}:changes/{version}/delivery.json", check=False)
        identity_at(repo, source, ref=release, archived=published.returncode == 0)
        return release
    raise MDFError("集成历史缺少发布 SHA", code="release_head_unreachable")


def release_anchor(head):
    return f"MDF-Release-Head: {head}"


def require_direct_pr(repo, source):
    """release 源分支直接 PR 前核验；主线前进时要求独立集成并增量验收。"""
    if not (is_github_flow(repo) and branch_details(source)["kind"] == "release"):
        return
    from mdf_core.lifecycle.release_publish import require_published_source
    require_published_source(repo, branch_details(source)["version"], source)
    trunk = trunk_branch(repo)
    if not ancestor(repo, f"refs/remotes/origin/{trunk}", source):
        version = branch_details(source)["version"]
        raise MDFError(f"release/{version} 尚未集成最新 {trunk}；先执行 release-integrate 并完成 catch-up",
                       code="integration_required", details={"integration": f"{PREFIX}{version}"})


def command_release_integrate(args):
    from mdf_core.lifecycle.pull_finish import finish_lock
    repo = repo_path(args.repo)
    require_git_root(repo)
    with finish_lock(repo):
        integrate(repo, args.source)


def integrate(repo, source):
    ensure_clean(repo)
    from mdf_core.workspace.merge_policy import configured
    source = source or current_branch(repo)
    details = branch_details(source)
    if not is_github_flow(repo) or configured(repo)["mode"] != "pr" or details["kind"] != "release":
        raise MDFError("release-integrate 仅用于 github-flow + pr 的 release 分支", code="invalid_closeout")
    version, trunk = details["version"], trunk_branch(repo)
    branch = f"{PREFIX}{version}"
    from mdf_core.lifecycle.pull_finish import Forge, origin
    git(repo, "fetch", "origin", "--prune")
    remote = f"refs/remotes/origin/{trunk}"
    current = sha(repo, source)
    from mdf_core.lifecycle.release_publish import require_published_source
    require_published_source(repo, version, source)
    forge = Forge(repo, origin(repo, configured(repo)["provider"]))
    pull = forge.find(branch, trunk)
    if pull and release_head_of(repo, branch, ref=pull["head"]) != current:
        raise MDFError("PR 已创建后 release_head 变化", code="release_head_changed",
                       details={"head": current})
    work = worktree_map(repo).get(branch)
    if work is None:
        work = sibling_worktree(repo, branch)
        if work.exists():
            raise MDFError("integration worktree 路径已存在", code="collision")
        work.parent.mkdir(parents=True, exist_ok=True)
        exists = git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0
        if not exists:
            tree = git(repo, "rev-parse", current + "^{tree}").stdout.strip()
            anchor = git(repo, "commit-tree", tree, "-p", current,
                         "-m", f"chore(release): 绑定 release/{version}", "-m", release_anchor(current)).stdout.strip()
            git(repo, "branch", branch, anchor)
        git(repo, "worktree", "add", str(work), branch)
    if git_in_progress_head(work):
        raise MDFError("integration 分支有未完成的 merge；解决并提交后重试", code="unfinished_merge",
                       details={"worktree": str(work)})
    ensure_clean(work)
    status = "up_to_date"
    anchored = release_head_of(work, branch)
    if anchored != current:
        if not ancestor(work, anchored, current) or ancestor(work, current, "HEAD"):
            raise MDFError("无法从集成历史核对新的 release_head", code="release_head_changed")
        message = f"chore(release): 纳入新的 release_head 到 release/{version}"
        result = git(work, "merge", "--no-ff", "--no-commit", "-m",
                     f"{message}\n\n{release_anchor(current)}", current, check=False)
        if result.returncode:
            conflicts = git(work, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
            raise MDFError("integration merge 冲突；在 worktree 解决后提交，再执行 $mdf pr",
                           code="merge_conflict", details={"worktree": str(work), "conflicts": conflicts})
        if git_in_progress_head(work):
            git(work, "commit", "--no-edit")
        status = "merged"
    if not ancestor(work, remote, "HEAD"):
        reopen_catchup(work)
        result = git(work, "merge", "--no-ff", "--no-commit", remote, check=False)
        if result.returncode:
            conflicts = git(work, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
            raise MDFError("integration merge 冲突；在 worktree 解决后提交，再执行 $mdf pr",
                           code="merge_conflict", details={"worktree": str(work), "conflicts": conflicts})
        if git_in_progress_head(work):
            git(work, "commit", "-m", f"chore(release): 集成 {trunk} 到 release/{version}")
        status = "merged"
    emit({"ok": True, "operation": "release-integrate", "branch": branch, "worktree": str(work),
          "release_head": current, "status": status, "next_intent": "catch-up"})


def reopen_catchup(repo):
    from mdf_core.lifecycle.delivery_state import locate
    from mdf_core.lifecycle.stage_route import parse_items, _tick
    root, _ = locate(repo)
    path = root / "objectives.md"
    text = path.read_text()
    item = next((i for i in parse_items(text) if i["name"] == "catch-up"), None)
    if item and item["checked"]:
        desired = _tick(text, item, "catch-up", {"baseline": sha(repo, "HEAD")})
        desired = desired.replace(f"- [x] {item['label']}", f"- [ ] {item['label']}", 1)
        path.write_text(desired)
        git(repo, "add", "--", str(path.relative_to(repo)))
        git(repo, "commit", "-m", "docs(release): 重新打开集成增量验收")
