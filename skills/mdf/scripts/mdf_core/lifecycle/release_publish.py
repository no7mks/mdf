"""github-flow release 在主线集成前发布固定 commit。"""
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.lifecycle.delivery_state import locate, read_json, write_json
from mdf_core.workspace.gitutil import current_branch, ensure_clean, repo_path, require_git_root
from mdf_core.workspace.merge_policy import ancestor, git, sha
from mdf_core.workspace.workflow_policy import is_github_flow


def published_head(repo, version, *, expected_oid=None):
    """核对本地 annotated tag 与远端 tag 对象一致。"""
    from mdf_core.lifecycle.closeout_render import require_tag_content
    tag = require_tag_content(repo, version)
    if expected_oid is not None and tag["oid"] != expected_oid:
        raise MDFError("final tag 对象与本次发布记录不符", code="tag_conflict")
    remote = git(repo, "ls-remote", "origin", f"refs/tags/v{version}").stdout.split()
    if not remote:
        raise MDFError("先执行 publish 创建并推送 final tag", code="release_not_published")
    if remote[0] != tag["oid"]:
        raise MDFError("本地与远端 final tag 不一致", code="tag_conflict")
    return tag["head"]


def publication_record_path(repo, source, version):
    from mdf_core.workspace.squash import common_dir
    return common_dir(repo) / "mdf/publication" / source / (str(version) + ".json")


def publication_record(repo, source, version):
    path = publication_record_path(repo, source, version)
    if not path.is_file():
        return None
    record = read_json(path)
    if record.get("source") != source or record.get("version") != version or not isinstance(record.get("head"), str):
        raise MDFError("发布记录的来源或版本不符", code="publication_state_changed")
    return record


def require_published_source(repo, version, ref, *, source):
    record = publication_record(repo, source, version)
    if not record or not record.get("published"):
        raise MDFError("先续办 publish，确认本轮固定候选已发布", code="release_not_published")
    head = published_head(repo, version, expected_oid=record.get("tag_oid"))
    if head != record["head"]:
        raise MDFError("final tag 与本轮固定发布 commit 不符", code="tag_conflict")
    if not ancestor(repo, head, ref):
        raise MDFError("源分支不包含已发布 commit", code="release_head_changed")
    return head


def command_publish(args):
    from mdf_core.lifecycle.pull_finish import finish_lock
    repo = repo_path(args.repo)
    require_git_root(repo)
    with finish_lock(repo):
        if is_github_flow(repo):
            from mdf_core.lifecycle.publish import support_merge_record
            from mdf_core.lifecycle.support_line import support_hotfix
            source = args.source or current_branch(repo)
            active_support = support_hotfix(repo, source)
            record = None
            if args.source and (not active_support or args.version):
                record = support_merge_record(repo, source, args.version)
            if record or active_support or (args.source and source.startswith("hotfix/")):
                result = publish_support(repo, record)
            else:
                result = publish_release(repo)
        else:
            result = publish_gitflow(repo, args.source or current_branch(repo), number=args.pull)
    emit({"ok": True, "operation": "publish", **result})


def publish_support(repo, receipt):
    from mdf_core.lifecycle.publish import merge_record_path, require_support_merge
    from mdf_core.lifecycle.pull_publish import tag_release
    if not receipt or not receipt[1].get("closed") or receipt[1].get("pending"):
        raise MDFError("support hotfix 须先完成 close-out", code="closeout_required")
    version, record = receipt
    merged = require_support_merge(repo, record)
    ref = f"refs/tags/v{version}"
    if (git(repo, "rev-parse", "--verify", ref, check=False).returncode
            and git(repo, "ls-remote", "origin", ref).stdout.strip()):
        git(repo, "fetch", "--no-tags", "origin", f"{ref}:{ref}")
    state = {"release_head": merged}
    tag_release(repo, state, version)
    published_head(repo, version, expected_oid=state["tag_oid"])
    write_json(merge_record_path(repo, record["source"], version), {**record, "published": True})
    return {"completed": True, "tag": state["tag"], "release_head": merged, "next_intent": None}


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
    start_head = sha(repo, "HEAD")
    receipt_path = publication_record_path(repo, source, version)
    receipt = publication_record(repo, source, version)
    remote_tag = git(repo, "ls-remote", "origin", ref).stdout.split()
    from mdf_core.lifecycle.catchup import require_synced
    if receipt is None:
        from mdf_core.lifecycle.consolidation import require_consolidated
        require_consolidated(repo, source)
        if not remote_tag:
            require_synced(repo, source)
        receipt = {"source": source, "version": version, "head": start_head, "published": False, "owned_tag": False}
        write_json(receipt_path, receipt)
    head = receipt["head"]
    if not ancestor(repo, head, "HEAD"):
        raise MDFError("工作分支不包含本次固定发布候选", code="release_head_changed")
    local = git(repo, "rev-parse", "--verify", ref, check=False)
    if local.returncode and remote_tag:
        git(repo, "fetch", "--no-tags", "origin", f"{ref}:{ref}")
        local = git(repo, "rev-parse", "--verify", ref)
    if local.returncode and receipt.get("tag_oid"):
        git(repo, "update-ref", ref, receipt["tag_oid"], "0" * 40)
        local = git(repo, "rev-parse", "--verify", ref)
    if not local.returncode:
        from mdf_core.lifecycle.closeout_render import require_tag_content
        tag = require_tag_content(repo, version, head)
        if receipt.get("tag_oid") and tag["oid"] != receipt["tag_oid"]:
            raise MDFError("本地 final tag 已偏离固定发布记录", code="tag_conflict")
    expected_remote = None
    if not remote_tag and not receipt["published"]:
        changed = git(repo, "diff", "--name-only", head, "HEAD").stdout.splitlines()
        if set(changed) - {path.relative_to(repo).as_posix()}:
            raise MDFError("候选生成后内容已变化，先重新 catch-up 与 consolidate", code="release_head_changed")
        expected_remote = require_synced(repo, source)
        from mdf_core.lifecycle.consolidation import require_consolidated
        require_consolidated(repo, source)
        if expected_remote and not ancestor(repo, expected_remote, head):
            raise MDFError("固定候选未包含远端同名分支，重新 catch-up 后发布", code="catchup_required")
    if not remote_tag and not receipt["published"]:
        from mdf_core.lifecycle.support_line import recheck_before_publish
        from mdf_core.workspace.workflow_policy import target_for
        recheck_before_publish(repo, source, version, target=target_for(repo, source, data=data), head=head)
    state = {"release_head": head}
    try:
        tag_release(repo, state, version, source=source if not receipt["published"] else None, expected_remote=expected_remote)
    finally:
        if state.get("tag_oid"):
            receipt["tag_oid"] = state["tag_oid"]
            receipt["owned_tag"] = receipt["owned_tag"] or state.get("created_tag", False)
            write_json(receipt_path, receipt)
    published = published_head(repo, version, expected_oid=receipt.get("tag_oid"))
    if published != head:
        raise MDFError("远端 tag 未指向固定发布候选", code="tag_conflict")
    receipt["published"] = True
    write_json(receipt_path, receipt)
    if sha(repo, "HEAD") != start_head:
        raise MDFError("tag 已发布，工作分支同时前进；保留现场后续办发布记录", code="pull_state_changed")
    ensure_clean(repo)
    if not item["checked"]:
        text = text.replace(f"- [ ] {item['label']}", f"- [x] {item['label']}", 1)
        path.write_text(text)
        git(repo, "add", "--", str(path.relative_to(repo)))
        git(repo, "commit", "--only", "-m", "docs(release): 记录 final tag 发布完成", "--", str(path.relative_to(repo)))
    from mdf_core.workspace.merge_policy import configured_delivery
    mode = configured_delivery(repo, source, data=data)["mode"]
    return {"completed": True, "tag": state["tag"], "release_head": head, "next_intent": "pr" if mode == "pr" else "merge"}


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
    require_published_source(repo, branch_details(source)["version"] or data.get("version"), "HEAD", source=source)
    git(repo, "add", "--", relative)
    git(repo, "commit", "-m", "docs(release): 续办 final tag 发布记录", "--", relative)


def publish_gitflow(repo, source, *, number=None):
    from mdf_core.workspace.gitutil import branch_details
    from mdf_core.workspace.merge_policy import configured, local_head
    from mdf_core.lifecycle.pull_publish import tag_release
    details = branch_details(source)
    if details["kind"] not in {"release", "hotfix"}:
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
