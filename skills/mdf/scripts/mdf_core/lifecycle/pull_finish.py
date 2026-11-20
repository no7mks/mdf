"""用平台 PR/MR 与 Git refs 执行提交、合并核验与清理。"""
from contextlib import contextmanager
import json
import os
import re

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.integrations.forge import Forge, origin
from mdf_core.lifecycle.roster import resolve_roster, role_branches
from mdf_core.workspace.gitutil import (
    branch_details, current_branch, ensure_clean, git_in_progress_head, primary_worktree, sibling_worktree, worktree_map,
)
from mdf_core.workspace.merge_policy import ancestor, git, local_head, sha
from mdf_core.workspace.pm import require_pm_diff, require_pm_merge, rework_branch


def preflight(repo, source):
    """沿用交付材料检查；由外层 intent 完成审查、验证及 fact。"""
    if current_branch(repo) != source:
        raise MDFError("首次提交或更新 PR/MR 必须在源 worktree 执行", code="stage_branch")
    from mdf_core.inspection.validate_records import require_fixed_outcomes
    kind = branch_details(source)["kind"]
    from mdf_core.workspace.workflow_policy import is_github_flow
    if is_github_flow(repo) and kind in {"release", "hotfix"}:
        from mdf_core.lifecycle.release_publish import require_published_source
        from mdf_core.lifecycle.delivery_state import locate
        _, data = locate(repo)
        version = branch_details(source)["version"] or data.get("version")
        require_published_source(repo, version, "HEAD", source=source)
    require_fixed_outcomes(repo, source)
    if kind == "adhoc":
        from mdf_core.lifecycle.adhoc_context import require_source
        require_source(source)
    if kind == "adhoc":
        from mdf_core.lifecycle.adhoc import completion
        roster = completion(repo, source)
    else:
        roster = resolve_roster(repo, source, kind)
    trees = worktree_map(repo)
    for name in role_branches(source, roster):
        if name in trees or not git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{name}", check=False).returncode:
            raise MDFError("角色分支尚未集成", code="roles_pending")
    if kind == "feature":
        from mdf_core.lifecycle.manual import feature_completion
        feature_completion(repo, source, allow_candidate=True)
    ensure_clean(repo)


def verified_merge(repo, pull, source, target, head):
    if pull["source"] != source or pull["target"] != target or pull["head"] != head:
        raise MDFError("PR/MR 的来源、目标或源提交已变化", code="pull_state_changed")
    merged = sha(repo, pull["merge_commit"])
    parents = git(repo, "show", "-s", "--format=%P", merged).stdout.split()
    if len(parents) != 2 or parents[1] != head:
        raise MDFError("PR/MR 必须保留源提交并使用双亲 merge commit", code="invalid_pull_merge")
    if not source.startswith(("pm/", "codex/sync/")):
        if not ancestor(repo, parents[0], head):
            raise MDFError("实际 PR merge 的 target 未先合回工作分支并验收", code="target_not_integrated")
        if git(repo, "diff", "--quiet", head, merged, check=False).returncode:
            raise MDFError("实际 PR merge 含已验收 source 之外的内容", code="invalid_pull_merge")
    remote = f"refs/remotes/origin/{target}"
    first = git(repo, "rev-list", "--first-parent", remote).stdout.split()
    if merged not in first:
        raise MDFError("merge commit 不在目标远端第一父链", code="pull_state_changed")
    return merged


def sync_local(repo, branch, *, integrate_develop=False):
    """默认同名 ff；close-out 可将远端集成到本地 develop，保留未共享工作。"""
    remote = f"refs/remotes/origin/{branch}"
    target = f"refs/heads/{branch}"
    remote_head = sha(repo, remote)
    occupant = worktree_map(repo).get(branch)
    if occupant:
        ensure_clean(occupant)
    local = git(repo, "rev-parse", "--verify", target, check=False)
    if local.returncode:
        git(repo, "branch", branch, remote_head)
        return
    local_head = local.stdout.strip()
    if local_head == remote_head:
        return
    if integrate_develop and branch == "develop":
        if ancestor(repo, remote_head, local_head):
            return
        if not ancestor(repo, local_head, remote_head):
            if occupant is None:
                occupant = sibling_worktree(repo, branch)
                occupant.parent.mkdir(parents=True, exist_ok=True)
                git(repo, "worktree", "add", str(occupant), branch)
            ensure_clean(occupant)
            result = git(occupant, "merge", "--no-ff", "-m",
                         "chore(closeout): 集成远端 develop 并保留本地工作", remote_head, check=False)
            if result.returncode:
                raise MDFError("本地 develop 集成失败，保留现场；解决并验证后续办 close-out",
                               code="merge_conflict" if git_in_progress_head(occupant) else "command_failed",
                               details={"worktree": str(occupant), "base": local_head,
                                        "remote_head": remote_head, "error": result.stderr.strip()})
            return
    if not ancestor(repo, local_head, remote_head):
        raise MDFError(f"本地 {branch} 与远端分歧，保留现场", code="upstream_diverged")
    if occupant:
        ensure_clean(occupant)
        git(occupant, "merge", "--ff-only", remote)
    else:
        git(repo, "update-ref", target, remote_head, local_head)


def remote_source_head(repo, source):
    ref = f"refs/heads/{source}"
    rows = git(repo, "ls-remote", "--refs", "origin", ref).stdout.splitlines()
    if not rows:
        return None
    if len(rows) != 1 or len(rows[0].split()) != 2 or rows[0].split()[1] != ref:
        raise MDFError("远端 source 查询结果不明确，保留现场", code="remote_cleanup_uncertain")
    return rows[0].split()[0]


def cleanup_remote(repo, source, head):
    """源提交须与平台已合并的 head 一致，删除时使用精确 lease。"""
    remote = remote_source_head(repo, source)
    if remote is None:
        return
    if remote != head:
        raise MDFError("远端 source 已变化，保留分支", code="pull_state_changed")
    ref = f"refs/heads/{source}"
    result = git(repo, "push", "--no-follow-tags", f"--force-with-lease={ref}:{head}",
                 "origin", f":{ref}", check=False)
    remaining = remote_source_head(repo, source)
    if remaining not in (None, head):
        raise MDFError("远端 source 在删除期间变化，保留现场", code="pull_state_changed")
    if remaining is not None:
        raise MDFError("远端 source 删除未确认，保留现场", code="remote_cleanup_uncertain",
                       details={"error": result.stderr.strip()})


def cleanup(repo, state):
    primary = primary_worktree(repo)
    source = state["source"]
    occupant = worktree_map(repo).get(source)
    if occupant is not None:
        ensure_clean(occupant)
        if sha(repo, source) != state["head"]:
            raise MDFError("源分支已变化，不能清理", code="pull_state_changed")
        git(occupant, "checkout", "--detach", state["head"])
        state["retained_worktree"] = str(occupant)
    present = git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{source}", check=False)
    if not present.returncode:
        if sha(repo, source) != state["head"]:
            raise MDFError("源分支已变化，不能删除", code="pull_state_changed")
        if source in worktree_map(repo):
            raise MDFError("源分支已被其他 worktree 占用，保留现场", code="pull_state_changed")
        deleted = git(primary, "update-ref", "-d", f"refs/heads/{source}", state["head"], check=False)
        if deleted.returncode:
            raise MDFError("源分支删除时已变化或被锁定，保留现场", code="pull_state_changed")
    remaining = git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{source}", check=False)
    if remaining.returncode == 0:
        raise MDFError("源分支已被重新创建，保留 ref 和配置", code="pull_state_changed")
    if remaining.returncode != 1:
        raise MDFError("无法核验源分支删除结果，保留现场", code="command_failed")
    section = git(primary, "config", "--local", "--get-regexp", rf"^branch\.{re.escape(source)}\.", check=False)
    if section.returncode == 0:
        git(primary, "config", "--local", "--remove-section", f"branch.{source}")
    elif section.returncode != 1:
        raise MDFError("无法读取已删除分支的配置，保留现场", code="command_failed")


def confirm_pull(pull, source, target, head):
    if pull["source"] != source or pull["target"] != target or pull["head"] != head:
        raise MDFError("PR/MR 的来源、目标或源提交已变化", code="pull_state_changed")


def check_source(repo, state):
    """发布或清理前核对源现场，不先产生 tag 或回合副作用。"""
    occupant = worktree_map(repo).get(state["source"])
    if occupant is not None:
        ensure_clean(occupant)
    current = git(repo, "rev-parse", "--verify", f"refs/heads/{state['source']}", check=False)
    if not current.returncode and current.stdout.strip() != state["head"]:
        raise MDFError("已合并 PR/MR 之外仍有源提交，保留现场", code="pull_state_changed")


@contextmanager
def finish_lock(repo):
    """锁住同一 Git common dir 的 PR 收口；进程退出时由 OS 自动释放。"""
    from mdf_core.workspace.squash import common_dir
    path = common_dir(repo) / "mdf/.finish.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt
                if path.stat().st_size == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise MDFError("另一个 PR、sync 或 pm 操作正在使用此仓库，请稍后重试", code="finish_busy") from exc
        yield


def require_feature_identity(repo, source, ref):
    """从固定 source commit 校验 feature 身份；恢复不依赖本地分支或 worktree。"""
    slug = branch_details(source)["slug"]
    record = git(repo, "show", f"{ref}:changes/unreleased/{slug}/delivery.json", check=False)
    if record.returncode:
        raise MDFError("feature 交付记录缺失", code="invalid_delivery")
    try:
        data = json.loads(record.stdout)
    except ValueError as exc:
        raise MDFError("feature 交付记录无效", code="invalid_delivery") from exc
    if not isinstance(data, dict) or data.get("branch") != source or data.get("slug") != slug:
        raise MDFError("feature 交付身份不匹配", code="invalid_delivery")


def lookup_pull(repo, forge, source, *, number=None):
    from mdf_core.workspace.workflow_policy import target_for
    head = local_head(repo, source)
    if number is not None and number <= 0:
        raise MDFError("--pull 需要正整数 ID", code="invalid_arguments")
    if number is not None:
        pull = forge.get(number)
        if pull["source"] != source:
            raise MDFError("PR/MR 与指定的 source 不符", code="pull_state_changed")
    else:
        details = branch_details(source)
        exact = head if details["kind"] == "hotfix" and details["version"] is None else None
        pull = forge.find(source, None, head=exact)
    if pull is None:
        return None, target_for(repo, source) if head is not None else None
    ref = pull["head"] if pull["state"] == "merged" else head
    if branch_details(source)["kind"] == "feature":
        require_feature_identity(repo, source, ref)
    target = target_for(repo, source, ref=ref)
    if pull["source"] != source or pull["target"] != target:
        raise MDFError("PR/MR 与交付的来源或目标不符", code="pull_state_changed")
    return pull, target


def finish(repo, source, settings, *, phase="close-out", number=None):
    with finish_lock(repo):
        _finish(repo, source, settings, phase=phase, number=number)


def submit(repo, forge, source, target, pull, *, pm, fixed_head):
    from mdf_core.workspace.squash import require_ready
    head = local_head(repo, source)
    if head is None:
        raise MDFError("未合并的源分支不存在", code="missing_branch")
    if pull and fixed_head and head != pull["head"]:
        raise MDFError("PR 已创建后 release_head 变化", code="release_head_changed",
                       details={"release_head": pull["head"], "head": head})
    if pull and not ancestor(repo, pull["head"], head):
        raise MDFError("源分支历史已改写", code="pull_state_changed")
    remote = f"refs/remotes/origin/{target}"
    if pull is None and ancestor(repo, head, remote):
        raise MDFError("没有未合入提交；不创建 PR 或删除分支", code="no_pending_commits")
    if pm:
        require_pm_diff(repo, remote, head)
    elif pull is None or head != pull["head"]:
        preflight(repo, source)
        head = sha(repo, f"refs/heads/{source}")
    if not pm:
        from mdf_core.lifecycle.support_line import ensure_remote_support_target
        ensure_remote_support_target(repo, source, target)
        if current_branch(repo) == source:
            from mdf_core.lifecycle.target_integration import require_integrated
            accepted = require_integrated(repo, source, target)
            head = accepted["head"]
        elif not ancestor(repo, remote, head):
            raise MDFError("在工作分支合回最新 target 并增量验收", code="integration_required")
    require_ready(repo, source)
    if local_head(repo, source) != head:
        raise MDFError("源分支在提交期间变化", code="pull_state_changed")
    remote_head = remote_source_head(repo, source)
    if pull and remote_head is None:
        raise MDFError("未合并 PR/MR 的远端 source 不存在", code="pull_state_changed")
    if remote_head and (not ancestor(repo, remote_head, head) or (pull and not ancestor(repo, pull["head"], remote_head))):
        raise MDFError("远端 source 与待提交历史不符", code="pull_state_changed")
    git(repo, "push", "--no-follow-tags", "origin", f"{head}:refs/heads/{source}")
    if pull is None:
        pull = forge.create(source, target, f"chore(delivery): 合入 {source}",
                            "MDF 交付；合并时请保留双亲 merge commit。")
    else:
        pull = forge.get(pull["id"])
    confirm_pull(pull, source, target, head)
    return pull


def retained_owner(repo, source, head):
    work = sibling_worktree(repo, source)
    listing = git(repo, "worktree", "list", "--porcelain", "-z").stdout
    for entry in listing.split("\0\0"):
        fields = entry.split("\0")
        if fields[0] == f"worktree {work}" and f"HEAD {head}" in fields and "detached" in fields and work.is_dir():
            return work
    return None


def _finish(repo, source, settings, *, phase, number):
    details = branch_details(source)
    if details["kind"] == "adhoc":
        from mdf_core.lifecycle.adhoc_context import require_source
        require_source(source)
    from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch
    github, trunk = is_github_flow(repo), trunk_branch(repo)
    pm = details["kind"] == "pm"
    if source.startswith("pm/rework/"):
        raise MDFError("pm PR 须使用原 source ref", code="unsupported_branch")
    if pm:
        if repo != primary_worktree(repo) or current_branch(repo) != trunk or source in worktree_map(repo):
            raise MDFError("pm 的 PR 与 close-out 须在主 trunk worktree 执行", code="not_on_trunk")
        if local_head(repo, rework_branch(source)) is not None:
            raise MDFError("先完成 pm finish-rework，再续办原 PR", code="pm_rework_pending")
    forge = Forge(repo, origin(repo, settings["provider"]))
    git(repo, "fetch", "origin", "--prune")
    pull, target = lookup_pull(repo, forge, source, number=number)
    if phase == "close-out" and (pull is None or pull["state"] != "merged"):
        raise MDFError("PR/MR 尚未 merged；由 pr intent 继续推进", code="pr_not_merged")
    publishes = details["kind"] in {"release", "hotfix"} and (github or target == trunk)
    if pull is None or pull["state"] == "open":
        if target is None:
            raise MDFError("源分支不存在，也未发现对应 PR/MR", code="missing_branch")
        pull = submit(repo, forge, source, target, pull, pm=pm, fixed_head=False)
    owner = worktree_map(repo).get(source) or retained_owner(repo, source, pull["head"])
    state = {"source": source, "target": target, "head": pull["head"],
             "retained_worktree": str(owner) if owner is not None else None}
    status = "waiting_for_merge" if pull["state"] == "open" else "closed_without_merge"
    if pull["state"] == "merged":
        check_source(repo, state)
        git(repo, "fetch", "origin", "--prune")
        merged = verified_merge(repo, pull, source, target, state["head"])
        if pm:
            require_pm_merge(repo, f"{merged}^1", state["head"], merged)
        if phase == "pr":
            emit({"ok": True, "operation": "pr", "mode": "pr", "source": source,
                  "completed": True, "status": "merged", "pull_request": pull,
                  "merge_commit": merged, "next_intent": "publish" if publishes and not github else "close-out"})
            return
        state["merge_commit"] = merged
        remote_head = remote_source_head(repo, source)
        local = local_head(repo, source)
        if remote_head is not None and (remote_head != state["head"] or local is None):
            raise MDFError("远端 source 的归属或 SHA 与本次交付不符，保留现场", code="pull_state_changed")
        if details["kind"] == "adhoc" and local is not None:
            from mdf_core.lifecycle.adhoc_context import material
            owner = worktree_map(repo).get(source)
            if owner is not None:
                _, ledger = material(owner, source)
                if not ledger:
                    from mdf_core.lifecycle.adhoc import completion
                    completion(owner, source)
        for branch in ([trunk, "develop"] if publishes and not github else [target]):
            occupant = worktree_map(repo).get(branch)
            if occupant:
                ensure_clean(occupant)
        sync_local(repo, target, integrate_develop=True)
        ready = True
        if publishes:
            from mdf_core.lifecycle.pull_publish import publish
            if details["kind"] == "hotfix" and details["version"] is None:
                from mdf_core.lifecycle.hotfix_version import source_version
                details["version"] = source_version(repo, source, ref=state["head"])
            if github:
                state["release_head"] = state["head"]
                if details["kind"] in {"release", "hotfix"}:
                    from mdf_core.lifecycle.release_publish import require_published_source
                    state["release_head"] = require_published_source(repo, details["version"], state["release_head"], source=source)
            ready = publish(repo, state, details["version"], source_cleaned=remote_head is None and local is None)
        if ready:
            cleanup_remote(repo, source, state["head"])
            cleanup(repo, state)
            status = "completed"
        else:
            status = "published_pending_backmerge"
    completed = status == "completed"
    emit({"ok": True, "operation": "pr" if phase == "pr" else "finish-gitflow", "mode": "pr", "source": source,
          "completed": completed, "status": status, "pull_request": pull,
          "merge_commit": state.get("merge_commit"), "backmerge": state.get("backmerge"),
          "tag": state.get("tag"), "targets": [target] + (["develop"] if target == trunk and not github else []),
          "remote_deleted": completed, "deleted": source if completed else None, "pushed": True,
          "retained_worktree": state["retained_worktree"], "primary_worktree": str(primary_worktree(repo))})
