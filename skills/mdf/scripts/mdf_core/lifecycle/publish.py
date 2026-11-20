"""本地发布从 Git 合并拓扑与实际 tag 核对每一步。"""
from mdf_core.foundation.errors import MDFError
from mdf_core.workspace.gitutil import ensure_clean, primary_worktree, worktree_map
from mdf_core.workspace.merge_policy import ancestor, git, local_head, sha


def find_merge(repo, target, head):
    """沿目标第一父链寻找以固定源提交为第二父的双亲 merge。"""
    rows = git(repo, "rev-list", "--first-parent", "--merges", "--parents", target).stdout.splitlines()
    return next((parts[0] for row in rows if len(parts := row.split()) == 3 and parts[2] == head), None)


def published_source(repo, version, target):
    from mdf_core.workspace.workflow_policy import is_github_flow
    tag_commit = sha(repo, f"refs/tags/v{version}")
    if is_github_flow(repo):
        return tag_commit
    parents = git(repo, "show", "-s", "--format=%P", tag_commit).stdout.split()
    if len(parents) != 2 or find_merge(repo, target, parents[1]) != tag_commit:
        raise MDFError("无法从发布 tag 核对源提交", code="publish_state_changed")
    return parents[1]


def publish(repo, source, version, *, head=None):
    from mdf_core.lifecycle.support_line import recheck_before_publish
    from mdf_core.workspace.gitflow import _git, _merge
    from mdf_core.lifecycle.closeout_render import changelog_excerpt, release_tag_message

    from mdf_core.workspace.workflow_policy import is_github_flow
    github = is_github_flow(repo)
    tag = f"refs/tags/v{version}"
    separate_release = github and source.startswith("release/")
    if separate_release:
        from mdf_core.lifecycle.release_publish import published_head
        published_head(repo, version)
    checked_source = local_head(repo, source)
    if head is None and checked_source is None and github:
        head = sha(repo, tag)
        from mdf_core.lifecycle.late_decision import identity_at
        if source.startswith("hotfix/"):
            from mdf_core.lifecycle.hotfix_version import delivery_record
            if delivery_record(repo, source, ref=head) is None:
                raise MDFError("发布 tag 缺少该 hotfix 的交付材料", code="publish_state_changed")
        else:
            archived = git(repo, "cat-file", "-e", f"{head}:changes/{version}/delivery.json", check=False)
            identity_at(repo, source, ref=head, archived=archived.returncode == 0)
    from mdf_core.lifecycle.late_decision import target_for
    target = target_for(repo, source, ref=head)
    ref = f"refs/heads/{target}"
    head = head or checked_source or published_source(repo, version, ref)
    if checked_source is not None and checked_source != head:
        raise MDFError("源分支已变化，保留现场", code="publish_state_changed")
    if separate_release:
        from mdf_core.lifecycle.release_publish import require_published_source
        require_published_source(repo, version, head)
    recheck_before_publish(repo, source, version, target=target, head=head)
    primary = primary_worktree(repo)
    current = sha(repo, ref)
    remote_refs = dict(line.split()[::-1] for line in _git(repo, "ls-remote", "--refs", "origin", ref, tag).stdout.splitlines())
    remote_head = remote_refs.get(ref)
    if remote_head is None and github and target.startswith("support/"):
        _git(repo, "push", "origin", f"{current}:{ref}")
        remote_head = current
    local_tag = _git(repo, "rev-parse", "--verify", "--quiet", tag, check=False).stdout.strip()
    if remote_refs.get(tag) not in (None, local_tag):
        raise MDFError("远端发布 tag 有冲突", code="publish_state_changed")
    merged = find_merge(repo, ref, head)
    if merged is None and github and ancestor(repo, head, current):
        merged = head
    if local_tag and not separate_release and (merged is None or _git(repo, "cat-file", "-t", tag).stdout.strip() != "tag"
                      or sha(repo, tag) != (head if github else merged)):
        raise MDFError("发布 tag 与源提交不符", code="publish_state_changed")
    if merged is None:
        if remote_head != current or checked_source is None or ancestor(repo, head, current):
            raise MDFError("无法核对当前发布分支和源提交", code="publish_state_changed")
        work = worktree_map(primary).get(target, primary)
        ensure_clean(work)
        _merge(work, head, target)
        merged = current = sha(repo, ref)
    if separate_release:
        from mdf_core.lifecycle.release_publish import require_published_source
        require_published_source(repo, version, head)
        if remote_head != current:
            _git(primary, "push", "origin", f"{current}:{ref}")
        return head
    if remote_refs.get(tag) == local_tag and local_tag:
        if not remote_head or not ancestor(repo, merged, remote_head):
            raise MDFError("远端版本 tag 与发布分支历史不一致", code="publish_state_changed")
    elif current != merged or (remote_head != merged and remote_head != sha(repo, merged + "^1")):
        raise MDFError("发布分支已变化，请核对当前 ref", code="publish_state_changed")
    if not local_tag:
        tag_commit = head if github else merged
        shown = _git(repo, "show", f"{tag_commit}:CHANGELOG.md", check=False)
        if shown.returncode:
            raise MDFError("发布提交缺少 CHANGELOG.md", code="missing_changelog")
        message = release_tag_message(tag.removeprefix("refs/tags/"), changelog_excerpt(shown.stdout, version))
        _git(repo, "tag", "-a", tag.removeprefix("refs/tags/"), tag_commit, "--cleanup=verbatim", "-m", message)
    if not github and not ancestor(repo, merged, "refs/heads/develop"):
        work = worktree_map(primary).get("develop", primary)
        ensure_clean(work)
        _merge(work, merged, "develop")
    if remote_refs.get(tag) is None:
        _git(primary, "push", "--atomic", "origin", f"{merged}:{ref}", f"{tag}:{tag}")
    return head
