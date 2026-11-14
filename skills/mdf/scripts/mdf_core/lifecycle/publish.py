"""记录并核验发布的部分成功状态，恢复时不重做已完成的合并或 tag。"""
from pathlib import Path

from mdf_core.lifecycle.delivery_state import read_json, safe, write_json
from mdf_core.foundation.errors import MDFError
from mdf_core.workspace.gitutil import current_branch, ensure_clean, primary_worktree, worktree_map


def state_path(repo, source):
    from mdf_core.workspace.gitflow import _git
    common = Path(_git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    if source.startswith("integrate/") and source.count("/") == 1:
        return safe(common, common / "mdf/finish/integrate" / f"{source.split('/', 1)[1]}.json")
    if source.startswith("sync/history/"):
        return safe(common, common / "mdf/finish/sync/history" / f"{source.removeprefix('sync/history/')}.json")
    if source.startswith("sync/"):
        return safe(common, common / "mdf/finish/sync" / f"{source.removeprefix('sync/')}.json")
    from mdf_core.workspace.gitutil import branch_details
    details = branch_details(source)
    if details["kind"] == "hotfix" and details["version"] is None:
        from mdf_core.lifecycle.hotfix_version import delivery_record
        source_ref = f"refs/heads/{source}"
        if _git(repo, "rev-parse", "--verify", "--quiet", source_ref, check=False).returncode == 0:
            record = delivery_record(repo, source, ref=source_ref)
            start = record[1].get("start_commit") if record else None
        else:
            start = _git(repo, "config", "--local", "--get", f"mdf.hotfix-{details['slug']}",
                         check=False).stdout.strip()
        if not isinstance(start, str) or len(start) != 40 or any(c not in "0123456789abcdef" for c in start):
            raise MDFError("hotfix 缺少固定交付起点，不能选择恢复记录", code="invalid_delivery")
        return safe(common, common / "mdf/finish" / source / f"{start}.json")
    if details["kind"] == "adhoc":
        import hashlib
        return safe(common, common / "mdf/finish" / f"adhoc-{hashlib.sha256(source.encode()).hexdigest()}.json")
    return safe(common, common / "mdf/finish" / f"{source}.json")


def _is_ancestor(repo, older, newer):
    from mdf_core.workspace.gitflow import _git
    return _git(repo, "merge-base", "--is-ancestor", older, newer, check=False).returncode == 0


def publish_targets(repo, source):
    """(发布分支, 依次合入的目标)：gitflow 为 trunk→develop，github-flow 仅 trunk 或 support/*。"""
    from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch
    trunk = trunk_branch(repo)
    if is_github_flow(repo):
        from mdf_core.lifecycle.late_decision import target_for
        branch = target_for(repo, source)
        return branch, (branch,)
    return trunk, (trunk, "develop")


def publish(repo, source, version):
    from mdf_core.workspace.gitflow import _git, _exists, _merge, _synced
    primary = primary_worktree(repo)
    master, targets = publish_targets(repo, source)
    github = len(targets) == 1
    path = state_path(repo, source)
    state = read_json(path) if path.exists() else None
    tag = f"v{version}"
    source_ref = f"refs/heads/{source}"
    head = _git(repo, "rev-parse", "--verify", source_ref, check=False)
    if state is None:
        if head.returncode:
            raise MDFError("发布源分支不存在", code="missing_branch")
        if github and master.startswith("support/") and not _exists(repo, f"refs/remotes/origin/{master}"):
            # 惰性切出的维护线首次发布：先把分支本身推到 origin，再按常规核验同步。
            _git(repo, "push", "origin", master)
        _synced(repo, master)
        remote_tag = _git(repo, "ls-remote", "--tags", "origin", f"refs/tags/{tag}").stdout
        if _exists(repo, f"refs/tags/{tag}") or remote_tag.strip():
            raise MDFError("版本 tag 已存在", code="tag_exists")
        state = {"source": source, "head": head.stdout.strip(), "tag": tag,
                 "origin": _git(repo, "remote", "get-url", "origin").stdout.strip(),
                 "before": {target: _git(repo, "rev-parse", target).stdout.strip() for target in targets},
                 "merged": {}, "pushed": False, "publish_branch": master}
        if github:
            state["release_head"] = state["head"]
        write_json(path, state)
    elif (state.get("source") != source or state.get("tag") != tag
          or state.get("origin") != _git(repo, "remote", "get-url", "origin").stdout.strip()
          or (not head.returncode and head.stdout.strip() != state.get("head"))
          or (head.returncode and not state.get("pushed"))):
        raise MDFError("发布现场与恢复记录不一致", code="publish_state_changed")

    if state.get("publish_branch", master) != master:
        raise MDFError("发布目标与恢复记录不一致", code="publish_state_changed")
    for target in targets:
        incoming = state["head"] if target == master else state["merged"][master]
        before = state["before"][target]
        current = _git(repo, "rev-parse", target).stdout.strip()
        remote = _git(repo, "rev-parse", f"origin/{master}").stdout.strip() if target == master else None
        recorded = state["merged"].get(target)
        if target == "develop" and recorded is None and current != before:
            parents = _git(repo, "show", "-s", "--format=%P", current).stdout.split()
            # 精确匹配的未记录合并仍走恢复；正常开发进度成为新的合并基线。
            if parents != [before, incoming]:
                before = current
                state["before"][target] = before
                write_json(path, state)
        if current == before and recorded is None:
            if target == master and remote != before:
                raise MDFError("远端分支已变化", code="publish_state_changed")
            occupant = worktree_map(primary).get(target)
            # 目标没有 checkout 时在主 worktree 合并，保留源 worktree 的分支身份。
            work = occupant if occupant is not None else primary
            ensure_clean(work)
            _merge(work, incoming, target)
            current = _git(repo, "rev-parse", target).stdout.strip()
        elif recorded is None:
            # 合并成功但写记录前中断：只接受精确的双亲合并提交。
            parents = _git(repo, "show", "-s", "--format=%P", current).stdout.split()
            # github-flow 允许冲突解决后的集成提交：只要仍包含 before 与 release_head 即可。
            integrated = github and _is_ancestor(repo, before, current) and _is_ancestor(repo, incoming, current)
            if (parents != [before, incoming] and not integrated) or (
                    target == master and remote not in (before, current)):
                raise MDFError("未记录的分支变化，不能自动恢复", code="publish_state_changed")
        elif current != recorded or (target == master and remote not in (before, recorded)):
            raise MDFError("发布分支被其他操作改变", code="publish_state_changed")
        state["merged"][target] = current
        write_json(path, state)
        if target == master:
            # github-flow 的 tag 固定在 release_head；绝不由合并提交的父链下标反推。
            tag_commit = state["release_head"] if github else current
            if github and not _is_ancestor(repo, tag_commit, current):
                raise MDFError("release_head 不是发布分支的祖先，不能标记发布完成",
                               code="release_head_unreachable")
            if _exists(repo, f"refs/tags/{tag}"):
                kind = _git(repo, "cat-file", "-t", f"refs/tags/{tag}").stdout.strip()
                tagged = _git(repo, "rev-parse", f"refs/tags/{tag}^{{commit}}").stdout.strip()
                if kind != "tag" or tagged != tag_commit:
                    raise MDFError("发布 tag 与已合并提交不符", code="publish_state_changed")
            else:
                shown = _git(
                    repo, "show", f"{tag_commit}:CHANGELOG.md", check=False
                )
                if shown.returncode:
                    raise MDFError(
                        "发布提交缺少 CHANGELOG.md，不能创建发布 tag",
                        code="missing_changelog",
                    )
                from mdf_core.lifecycle.closeout_render import changelog_excerpt, release_tag_message
                message = release_tag_message(
                    tag, changelog_excerpt(shown.stdout, version)
                )
                # verbatim：默认 strip 会丢掉 CHANGELOG 里以 # 开头的标题行。
                _git(
                    repo,
                    "tag",
                    "-a",
                    tag,
                    tag_commit,
                    "--cleanup=verbatim",
                    "-m",
                    message,
                )

    remote_refs = dict(line.split()[::-1] for line in _git(
        repo, "ls-remote", "origin", f"refs/heads/{master}",
        f"refs/tags/{tag}").stdout.splitlines())
    tag_object = _git(repo, "rev-parse", f"refs/tags/{tag}").stdout.strip()
    expected = {f"refs/heads/{master}": state["merged"][master], f"refs/tags/{tag}": tag_object}
    if remote_refs != expected:
        if (remote_refs.get(f"refs/tags/{tag}") not in (None, tag_object)
                or remote_refs.get(f"refs/heads/{master}") not in
                (state["before"][master], state["merged"][master])):
            raise MDFError("远端发布状态有冲突", code="publish_state_changed")
        _git(primary, "push", "--atomic", "origin", master, f"refs/tags/{tag}")
    state["pushed"] = True
    write_json(path, state)
    return state
