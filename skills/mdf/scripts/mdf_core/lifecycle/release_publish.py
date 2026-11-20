"""github-flow release 在主线集成前发布固定 commit。"""
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.lifecycle.delivery_state import locate
from mdf_core.workspace.gitutil import current_branch, ensure_clean, repo_path, require_git_root
from mdf_core.workspace.merge_policy import ancestor, git, sha
from mdf_core.workspace.workflow_policy import is_github_flow


def published_head(repo, version):
    """核对本地 annotated tag 与远端 tag 对象一致。"""
    from mdf_core.lifecycle.closeout_render import require_tag_content
    tag = require_tag_content(repo, version)
    remote = git(repo, "ls-remote", "origin", f"refs/tags/v{version}").stdout.split()
    if not remote:
        raise MDFError("先执行 publish 创建并推送 final tag", code="release_not_published")
    if remote[0] != tag["oid"]:
        raise MDFError("本地与远端 final tag 不一致", code="tag_conflict")
    return tag["head"]


def require_published_source(repo, version, ref):
    head = published_head(repo, version)
    if not ancestor(repo, head, ref):
        raise MDFError("源分支不包含已发布 commit", code="release_head_changed")
    return head


def command_publish(args):
    from mdf_core.lifecycle.pull_finish import finish_lock
    repo = repo_path(args.repo)
    require_git_root(repo)
    with finish_lock(repo):
        if is_github_flow(repo):
            result = publish_release(repo)
        else:
            result = publish_gitflow(repo, args.source or current_branch(repo), number=args.pull)
    emit({"ok": True, "operation": "publish", **result})


def publish_release(repo):
    from mdf_core.lifecycle.pull_publish import tag_release
    from mdf_core.lifecycle.stage_route import parse_items
    source = current_branch(repo)
    from mdf_core.workspace.gitutil import branch_details
    if branch_details(source)["kind"] not in {"release", "hotfix"}:
        raise MDFError("publish 需要版本发布分支", code="unsupported_branch")
    root, data = locate(repo)
    recover_publication_record(repo, root, source)
    ensure_clean(repo)
    version = branch_details(source)["version"] or data.get("version")
    path = root / "objectives.md"
    text = path.read_text()
    items = parse_items(text)
    item = next((item for item in items if item["name"] == "publish"), None)
    if item is None:
        raise MDFError("objectives 缺少 publish", code="invalid_objectives")
    pending = [i["name"] for i in items[:items.index(item)] if not i["checked"]]
    if pending:
        raise MDFError("publish 前置未完成", code="stage_prerequisite", details={"pending": pending})
    ref = f"refs/tags/v{version}"
    exists = git(repo, "rev-parse", "--verify", ref, check=False).returncode == 0
    head = sha(repo, ref) if exists else sha(repo, "HEAD")
    remote_tag = git(repo, "ls-remote", "origin", ref).stdout.strip()
    if exists:
        if not ancestor(repo, head, "HEAD"):
            raise MDFError("final tag 与 release 不符", code="tag_conflict")
        changed = git(repo, "diff", "--name-only", head, "HEAD").stdout.splitlines()
        if not remote_tag and set(changed) - {path.relative_to(repo).as_posix()}:
            raise MDFError("final tag 创建后发布内容已变化", code="release_head_changed")
    from mdf_core.lifecycle.catchup import require_synced
    expected_remote = None if remote_tag else require_synced(repo, source)
    if not remote_tag:
        from mdf_core.lifecycle.consolidation import require_consolidated
        require_consolidated(repo, source)
    if not remote_tag and expected_remote and not ancestor(repo, expected_remote, head):
        raise MDFError("本地候选 tag 未包含远端 release，重新定版后发布", code="catchup_required")
    state = {"release_head": head}
    try:
        tag_release(repo, state, version, source=source, expected_remote=expected_remote)
    finally:
        if not exists:
            from mdf_core.lifecycle.catchup import state_path
            from mdf_core.lifecycle.delivery_state import read_json, write_json
            candidate = git(repo, "rev-parse", "--verify", ref, check=False)
            if not candidate.returncode:
                sync_path = state_path(repo, source)
                sync_state = read_json(sync_path)
                sync_state["candidate_tag"] = candidate.stdout.strip()
                write_json(sync_path, sync_state)
    published_head(repo, version)
    if not item["checked"]:
        text = text.replace(f"- [ ] {item['label']}", f"- [x] {item['label']}", 1)
        path.write_text(text)
        git(repo, "add", "--", str(path.relative_to(repo)))
        git(repo, "commit", "-m", "docs(release): 记录 final tag 发布完成")
    return {"completed": True, "tag": state["tag"], "release_head": head, "next_intent": "pr" if configured_mode(repo) == "pr" else "merge"}


def recover_publication_record(repo, root, source):
    """仅续办已发布事务留下的精确 objectives 勾选改动。"""
    from mdf_core.lifecycle.stage_route import _dirty_names, _tick, parse_items
    dirty = set(_dirty_names(repo))
    if not dirty:
        return
    path = root / "objectives.md"
    relative = path.relative_to(repo).as_posix()
    if dirty != {relative}:
        ensure_clean(repo)
    text = git(repo, "show", f"HEAD:{relative}").stdout
    item = next((i for i in parse_items(text) if i["name"] == "publish"), None)
    if item is None or item["checked"]:
        ensure_clean(repo)
    desired = _tick(text, item, "publish", {})
    staged = git(repo, "show", f":{relative}").stdout
    if path.read_text() != desired or staged not in (text, desired):
        ensure_clean(repo)
    from mdf_core.workspace.gitutil import branch_details
    _, data = locate(repo)
    require_published_source(repo, branch_details(source)["version"] or data.get("version"), "HEAD")
    git(repo, "add", "--", relative)
    git(repo, "commit", "-m", "docs(release): 续办 final tag 发布记录", "--", relative)


def configured_mode(repo):
    from mdf_core.workspace.merge_policy import configured
    return configured(repo)["mode"]


def publish_gitflow(repo, source, *, number=None):
    from mdf_core.workspace.gitutil import branch_details
    from mdf_core.workspace.merge_policy import configured, local_head
    from mdf_core.lifecycle.pull_publish import tag_release
    details = branch_details(source)
    if details["kind"] not in {"release", "hotfix", "on-demand-release"}:
        raise MDFError("publish 需要版本发布分支", code="unsupported_branch")
    version = details["version"]
    settings = configured(repo)
    if settings["mode"] == "pr":
        from mdf_core.lifecycle.pull_finish import Forge, origin, lookup_pull, verified_merge
        forge = Forge(repo, origin(repo, settings["provider"]))
        git(repo, "fetch", "origin", "--prune")
        pull, target = lookup_pull(repo, forge, source, number=number)
        if pull is None or pull["state"] != "merged":
            raise MDFError("先完成 PR merge 再发布", code="pr_not_merged")
        if version is None:
            from mdf_core.lifecycle.hotfix_version import source_version
            version = source_version(repo, source, ref=pull["head"])
        from mdf_core.lifecycle.pull_finish import check_source
        check_source(repo, {"source": source, "head": pull["head"]})
        merged = verified_merge(repo, pull, source, target, pull["head"])
    else:
        from mdf_core.lifecycle.delivery_state import read_json
        from mdf_core.lifecycle.publish import merge_record_path
        if version is None:
            from mdf_core.lifecycle.hotfix_version import source_version
            version = source_version(repo, source)
        path = merge_record_path(repo, source, version)
        if not path.is_file():
            raise MDFError("先执行 merge 再发布", code="merge_required")
        record = read_json(path)
        if record.get("pending"):
            raise MDFError("先完成 target 增量验收与 merge", code="integration_required")
        if local_head(repo, source) not in (None, record["head"]):
            raise MDFError("merge 后工作分支已变化", code="pull_state_changed")
        merged = record["merge_commit"]
        git(repo, "fetch", "origin", "--prune")
        if not ancestor(repo, merged, f"refs/remotes/origin/{record['target']}"):
            raise MDFError("远端主线尚未包含 merge commit", code="merge_required")
    tag_release(repo, {"merge_commit": merged}, version)
    published_head(repo, version)
    return {"completed": True, "tag": f"v{version}", "release_head": merged, "next_intent": "close-out"}
