"""github-flow release 在主线集成前发布固定 commit。"""
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.lifecycle.delivery_state import locate
from mdf_core.workspace.gitutil import current_branch, ensure_clean, repo_path, require_git_root
from mdf_core.workspace.merge_policy import ancestor, git, sha
from mdf_core.workspace.workflow_policy import is_github_flow


def published_head(repo, version):
    """核对本地 annotated tag 与远端 tag 对象一致。"""
    ref = f"refs/tags/v{version}"
    local = git(repo, "rev-parse", "--verify", ref, check=False)
    remote = git(repo, "ls-remote", "origin", ref).stdout.split()
    if local.returncode or not remote:
        raise MDFError("先执行 publish 创建并推送 final tag", code="release_not_published")
    if git(repo, "cat-file", "-t", ref).stdout.strip() != "tag" or remote[0] != local.stdout.strip():
        raise MDFError("本地与远端 final tag 不一致", code="tag_conflict")
    return sha(repo, ref)


def require_published_source(repo, version, ref):
    head = published_head(repo, version)
    if not ancestor(repo, head, ref):
        raise MDFError("源分支不包含已发布 commit", code="release_head_changed")
    changed = git(repo, "diff", "--name-only", head, ref).stdout.splitlines()
    allowed = {f"changes/{version}/objectives.md", f"changes/unreleased/{version}/objectives.md"}
    if set(changed) - allowed:
        raise MDFError("发布后 release 内容已变化；在独立集成分支处理后续修改", code="release_head_changed")
    return head


def command_publish(args):
    from mdf_core.lifecycle.pull_finish import finish_lock
    repo = repo_path(args.repo)
    require_git_root(repo)
    with finish_lock(repo):
        result = publish_release(repo)
    emit({"ok": True, "operation": "publish", **result})


def publish_release(repo):
    from mdf_core.lifecycle.pull_publish import tag_release
    from mdf_core.lifecycle.stage_route import parse_items
    source = current_branch(repo)
    if not is_github_flow(repo) or not source.startswith("release/"):
        raise MDFError("publish 适用于 github-flow release", code="unsupported_branch")
    root, data = locate(repo)
    recover_publication_record(repo, root, source)
    ensure_clean(repo)
    version = source.removeprefix("release/")
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
    if exists:
        if not ancestor(repo, head, "HEAD"):
            raise MDFError("final tag 与 release 不符", code="tag_conflict")
        changed = git(repo, "diff", "--name-only", head, "HEAD").stdout.splitlines()
        if set(changed) - {path.relative_to(repo).as_posix()}:
            raise MDFError("final tag 创建后发布内容已变化", code="release_head_changed")
    from mdf_core.lifecycle.sync_remote import require_synced
    remote_tag = git(repo, "ls-remote", "origin", ref).stdout.strip()
    expected_remote = None if remote_tag else require_synced(repo, source)
    if not remote_tag and expected_remote and not ancestor(repo, expected_remote, head):
        raise MDFError("本地候选 tag 未包含远端 release，重新定版后发布", code="sync_remote_required")
    state = {"release_head": head}
    try:
        tag_release(repo, state, version, source=source, expected_remote=expected_remote)
    finally:
        if not exists:
            from mdf_core.lifecycle.sync_remote import state_path
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
    return {"completed": True, "tag": state["tag"], "release_head": head, "next_intent": "catch-up"}


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
    require_published_source(repo, source.removeprefix("release/"), "HEAD")
    git(repo, "add", "--", relative)
    git(repo, "commit", "-m", "docs(release): 续办 final tag 发布记录", "--", relative)
