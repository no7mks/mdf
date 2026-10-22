"""PR/MR 提交、等待、核验与清理；操作记录不充当阶段 gate。"""
from pathlib import Path

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.integrations.forge import Forge, origin
from mdf_core.lifecycle.delivery_state import read_json, write_json
from mdf_core.lifecycle.publish import state_path
from mdf_core.lifecycle.roster import resolve_roster, role_branches
from mdf_core.workspace.gitutil import branch_details, current_branch, ensure_clean, primary_worktree, worktree_map
from mdf_core.workspace.merge_policy import ancestor, git, sha


def preflight(repo, source):
    """沿用交付材料检查；由外层 intent 完成审查、验证及 fact。"""
    if current_branch(repo) != source:
        raise MDFError("首次提交或更新 PR/MR 必须在源 worktree 执行", code="stage_branch")
    kind = branch_details(source)["kind"]
    if kind == "feature":
        from mdf_core.lifecycle.manual import feature_completion
        complete, roster = feature_completion(repo, source, allow_candidate=True)
    elif kind == "adhoc":
        from mdf_core.lifecycle.adhoc import completion
        complete, roster = None, completion(repo, source)
    else:
        complete, roster = None, resolve_roster(repo, source, kind)
    trees = worktree_map(repo)
    for name in role_branches(source, roster):
        if name in trees or not git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{name}", check=False).returncode:
            raise MDFError("角色分支尚未集成", code="roles_pending")
    if complete is not None:
        complete(repo)
        if git(repo, "diff", "--cached", "--name-only").stdout.strip():
            git(repo, "commit", "-m", "docs(delivery): 准备合入后的 Proposal 状态")
    ensure_clean(repo)


def verified_merge(repo, pull, source, target, head):
    if pull["source"] != source or pull["target"] != target or pull["head"] != head:
        raise MDFError("PR/MR 的来源、目标或源提交已变化", code="pull_state_changed")
    merged = sha(repo, pull["merge_commit"])
    parents = git(repo, "show", "-s", "--format=%P", merged).stdout.split()
    if len(parents) != 2 or parents[1] != head:
        raise MDFError("PR/MR 必须保留源提交并使用双亲 merge commit", code="invalid_pull_merge")
    remote = f"refs/remotes/origin/{target}"
    first = git(repo, "rev-list", "--first-parent", remote).stdout.split()
    if merged not in first:
        raise MDFError("merge commit 不在目标远端第一父链", code="pull_state_changed")
    return merged


def sync_local(repo, branch):
    """仅同名 ff 同步；不覆盖本地开发或他人 worktree。"""
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
    if not ancestor(repo, local_head, remote_head):
        raise MDFError(f"本地 {branch} 与远端分歧，保留现场", code="upstream_diverged")
    if occupant:
        ensure_clean(occupant)
        git(occupant, "merge", "--ff-only", remote)
    else:
        git(repo, "update-ref", target, remote_head, local_head)


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
        git(primary, "branch", "-D", source)


def finish(repo, source, settings):
    path = state_path(repo, source)
    state = read_json(path) if path.exists() else None
    identity = origin(repo, settings["provider"])
    forge = Forge(repo, identity)
    details = branch_details(source)
    target = "master" if details["kind"] in {"release", "hotfix"} else "develop"
    if state and (state.get("mode") != "pr" or state.get("identity") != identity
                  or state.get("source") != source or state.get("target") != target):
        raise MDFError("PR/MR 恢复记录与当前配置不符", code="pull_state_changed")
    if state is None:
        preflight(repo, source)
        state = {"mode": "pr", "identity": identity, "source": source, "target": target,
                 "head": sha(repo, source), "pull": None, "completed": False,
                 "retained_worktree": str(worktree_map(repo).get(source, repo))}
        write_json(path, state)
    git(repo, "fetch", "origin", "--prune")
    pull = forge.get(state["pull"]["id"]) if state.get("pull") else forge.find(source, target)
    if pull is None or pull["state"] == "open":
        current = git(repo, "rev-parse", "--verify", f"refs/heads/{source}", check=False)
        if current.returncode:
            raise MDFError("未合并的源分支不存在", code="missing_branch")
        head = current.stdout.strip()
        if head != state["head"]:
            if details["kind"] in {"release", "hotfix"}:
                raise MDFError("已准备发布的源提交已变化，保留版本目录", code="publish_state_changed")
            if not ancestor(repo, state["head"], head):
                raise MDFError("源分支历史已改写", code="pull_state_changed")
            preflight(repo, source)
            state["head"] = sha(repo, source)
            write_json(path, state)
        # 非 force 精确推送本次源提交；重复 push 为 noop。
        git(repo, "push", "--no-follow-tags", "origin", f"{state['head']}:refs/heads/{source}")
        if pull is None:
            pull = forge.create(source, target, f"chore(delivery): 合入 {source}",
                                "MDF 交付；请使用 merge commit。合并后再次执行 $mdf close-out 续办。")
        else:
            pull = forge.get(pull["id"])
    if pull["source"] != source or pull["target"] != target or pull["head"] != state["head"]:
        raise MDFError("PR/MR 与已准备交付不一致", code="pull_state_changed")
    state["pull"] = pull
    write_json(path, state)
    status = "waiting_for_merge" if pull["state"] == "open" else "closed_without_merge"
    if pull["state"] == "merged":
        git(repo, "fetch", "origin", "--prune")
        merged = verified_merge(repo, pull, source, target, state["head"])
        if state.get("merge_commit") not in (None, merged):
            raise MDFError("平台合并结果已变化", code="pull_state_changed")
        state["merge_commit"] = merged
        write_json(path, state)
        for branch in (["master", "develop"] if target == "master" else ["develop"]):
            occupant = worktree_map(repo).get(branch)
            if occupant:
                ensure_clean(occupant)
        sync_local(repo, target)
        ready = True
        if target == "master":
            from mdf_core.lifecycle.pull_publish import publish
            ready = publish(repo, state, details["version"], path)
        if ready:
            cleanup(repo, state)
            state["completed"] = True
            status = "completed"
        else:
            status = "published_pending_backmerge"
        write_json(path, state)
    emit({"ok": True, "operation": "finish-gitflow", "mode": "pr", "source": source,
          "completed": state["completed"], "status": status, "pull_request": pull,
          "merge_commit": state.get("merge_commit"), "backmerge": state.get("backmerge"),
          "tag": state.get("tag"), "targets": [target] + (["develop"] if target == "master" else []),
          "deleted": source if state["completed"] else None, "pushed": True,
          "retained_worktree": state.get("retained_worktree"), "primary_worktree": str(primary_worktree(repo))})
