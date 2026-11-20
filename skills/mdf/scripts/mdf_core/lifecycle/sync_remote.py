"""发布前同步远端同名 release，并固定增量验收的 commit。"""
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.lifecycle.delivery_state import locate, read_json, write_json
from mdf_core.lifecycle.stage_route import parse_items
from mdf_core.workspace.gitutil import current_branch, ensure_clean, repo_path, require_git_root
from mdf_core.workspace.merge_policy import ancestor, git, sha
from mdf_core.workspace.squash import common_dir
from mdf_core.workspace.workflow_policy import is_github_flow


def state_path(repo, source):
    return common_dir(repo) / "mdf/sync-remote" / (source.removeprefix("release/") + ".json")


def remote_head(repo, source):
    rows = git(repo, "ls-remote", "--heads", "origin", f"refs/heads/{source}").stdout.split()
    return rows[0] if rows else None


def require_synced(repo, source):
    path = state_path(repo, source)
    state = read_json(path) if path.is_file() else {}
    remote = remote_head(repo, source)
    if (state.get("completed_head") != sha(repo, "HEAD") or state.get("remote") != remote):
        raise MDFError("远端 release 或本地待发布内容已变化，先完成 sync-remote", code="sync_remote_required",
                       details={"next_intent": "sync-remote", "remote": remote})
    if remote and not ancestor(repo, remote, "HEAD"):
        raise MDFError("待发布 commit 未包含远端 release", code="sync_remote_required")
    return remote


def command_sync_remote(args):
    from mdf_core.lifecycle.pull_finish import finish_lock
    repo = repo_path(args.repo)
    require_git_root(repo)
    with finish_lock(repo):
        result = sync_remote(repo, complete=args.complete, reviewed_head=args.reviewed_head, summary=args.summary)
    emit({"ok": True, "operation": "sync-remote", **result})


def sync_remote(repo, *, complete=False, reviewed_head=None, summary=None):
    from mdf_core.lifecycle.catchup_plan import build_plan
    source = current_branch(repo)
    if not is_github_flow(repo) or not source.startswith("release/"):
        raise MDFError("sync-remote 适用于 github-flow release", code="unsupported_branch")
    version = source.removeprefix("release/")
    if git(repo, "ls-remote", "origin", f"refs/tags/v{version}").stdout.strip():
        raise MDFError("final tag 已发布，发布内容已冻结", code="release_already_published")
    root, data = locate(repo)
    objectives = root / "objectives.md"
    relative = objectives.relative_to(repo).as_posix()
    text = git(repo, "show", f"HEAD:{relative}").stdout if complete else objectives.read_text()
    items = parse_items(text)
    item = next((i for i in items if i["name"] == "sync-remote"), None)
    if item is None:
        raise MDFError("objectives 缺少 sync-remote", code="invalid_objectives")
    pending = [i["name"] for i in items[:items.index(item)] if not i["checked"]]
    if pending:
        raise MDFError("sync-remote 前置未完成", code="stage_prerequisite", details={"pending": pending})
    path = state_path(repo, source)
    if complete and not path.is_file():
        raise MDFError("先执行 sync-remote 取得增量验收计划", code="sync_remote_required")
    if complete:
        require_completion_worktree(repo, objectives, text, completion_text(text, item, sha(repo, "HEAD")))
    else:
        ensure_clean(repo)
    state = read_json(path) if path.is_file() else {"base": sha(repo, "HEAD")}
    if state.get("completed_head"):
        state["base"] = state["completed_head"]
    remote = remote_head(repo, source)
    if remote:
        git(repo, "fetch", "--no-tags", "origin", f"refs/heads/{source}")
        remote = sha(repo, "FETCH_HEAD")
    head = sha(repo, "HEAD")
    if complete:
        if not summary or not summary.strip() or reviewed_head != head:
            raise MDFError("完成同步须提供当前 reviewed-head 与增量验收 summary", code="sync_review_required")
        if remote and not ancestor(repo, remote, head):
            raise MDFError("远端 release 再次前进，重新执行 sync-remote 并补检", code="sync_remote_required")
    else:
        candidate = state.pop("candidate_tag", None)
        if candidate:
            git(repo, "update-ref", "-d", f"refs/tags/v{version}", candidate)
        state.pop("completed_head", None)
        state["remote"] = remote
        write_json(path, state)
        if item["checked"]:
            text = text.replace(f"- [x] {item['label']}", f"- [ ] {item['label']}", 1)
            objectives.write_text(text)
            git(repo, "add", "--", str(objectives.relative_to(repo)))
            git(repo, "commit", "-m", "docs(release): 重新核对远端同步")
        if remote and not ancestor(repo, remote, "HEAD"):
            merged = git(repo, "merge", "--no-edit", "--ff", "-m", "chore(release): 同步远端同名分支", remote, check=False)
            if merged.returncode:
                raise MDFError("远端 release 合并失败；解决冲突并提交后续办 sync-remote", code="merge_conflict",
                               details={"base": state["base"], "remote": remote})
        root, data = locate(repo)
    plan = build_plan(repo, root, data, explicit_base=state["base"])
    if complete:
        if state.get("completed_head") == head and state.get("remote") == remote and item["checked"]:
            ensure_clean(repo)
            return {"completed": True, "remote": remote, "plan": plan, "head": head, "next_intent": "publish"}
        desired = completion_text(text, item, head)
        if desired != text:
            objectives.write_text(desired)
            git(repo, "add", "--", str(objectives.relative_to(repo)))
            git(repo, "commit", "-m", "docs(release): 完成远端同步与增量验收")
        state.update(completed_head=sha(repo, "HEAD"), remote=remote, summary=summary)
        write_json(path, state)
    return {"completed": complete, "remote": remote, "plan": plan,
            "head": sha(repo, "HEAD"), "next_intent": "publish" if complete else "sync-remote"}


def completion_text(text, item, head):
    from mdf_core.lifecycle.catchup_plan import BASELINE
    from mdf_core.lifecycle.stage_route import _tick
    desired = _tick(text, item, "sync-remote", {})
    baseline = f"catch-up 基线：{head}"
    return BASELINE.sub(baseline, desired) if BASELINE.search(desired) else desired.rstrip() + "\n\n" + baseline + "\n"


def require_completion_worktree(repo, path, original, desired):
    from mdf_core.lifecycle.stage_route import _dirty_names
    dirty = set(_dirty_names(repo))
    if not dirty:
        return
    relative = path.relative_to(repo).as_posix()
    if (dirty != {relative} or path.read_text() != desired
            or git(repo, "show", f":{relative}").stdout not in (original, desired)):
        ensure_clean(repo)
