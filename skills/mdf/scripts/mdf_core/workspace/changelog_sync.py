"""support hotfix 发布记录的 pm PR 准备与完成核验。"""
import re
import json
import subprocess

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.foundation.textutil import stable_semver
from mdf_core.lifecycle.closeout_render import changelog_excerpt
from mdf_core.lifecycle.delivery_state import read_json, write_json
from mdf_core.lifecycle.release_publish import published_head
from mdf_core.workspace.gitutil import current_branch, ensure_clean, repo_path, require_git_root, sibling_worktree, worktree_map
from mdf_core.workspace.merge_policy import configured, git, local_head
from mdf_core.workspace.workflow_policy import is_github_flow, trunk_branch

PREFIX = "pm/patch-record-"


def sync_version(source):
    value = source.removeprefix(PREFIX) if source.startswith(PREFIX) else ""
    return value if stable_semver(value) else None


def trunk_policy(repo):
    """维护线配置可能过时；同步策略只读取最新远端 trunk。"""
    trunk = trunk_branch(repo)
    ref = f"refs/remotes/origin/{trunk}"
    git(repo, "fetch", "--no-tags", "origin", f"+refs/heads/{trunk}:{ref}")
    head = git(repo, "rev-parse", ref).stdout.strip()
    if not is_github_flow(repo, head) or trunk_branch(repo, head) != trunk:
        raise MDFError("远端 trunk 的 workflow 已变化", code="invalid_workflow")
    return trunk, head, configured(repo, head)


def blob_text(repo, ref, path):
    """Git 文本 helper 会转换 CRLF；发布记录比较必须保留原始字节。"""
    result = subprocess.run(["git", "cat-file", "blob", f"{ref}:{path}"], cwd=repo, capture_output=True, check=False)
    if result.returncode:
        raise MDFError(result.stderr.decode(errors="replace").strip(), code="command_failed")
    return result.stdout.decode("utf-8")


def state_path(repo, version):
    from mdf_core.workspace.squash import common_dir
    return common_dir(repo) / "mdf/changelog-sync" / f"{version}.json"


def sync_policy(repo, version):
    path = state_path(repo, version)
    if path.is_file():
        data = read_json(path)
        return data["target"], f"refs/remotes/origin/{data['target']}", data["settings"]
    return trunk_policy(repo)


def section(text, version):
    return changelog_excerpt(text.replace("\r\n", "\n"), version).strip()


def insert_section(text, version, excerpt):
    """只插入固定版本章节，其他章节逐字保留。"""
    headings = list(re.finditer(r"(?m)^##[ \t]+(?:\[([^\]]+)\]|([^\s]+))(?:[ \t]+-[ \t]+[^\r\n]*)?[ \t]*\r?$", text))
    for match in headings:
        other = match.group(1) or match.group(2)
        if other == version:
            if section(text, version) != excerpt.replace("\r\n", "\n").strip():
                raise MDFError("同版本 CHANGELOG 内容与发布记录不一致", code="changelog_conflict")
            return text
    at = next((m.start() for m in headings if stable_semver(m.group(1) or m.group(2))
               and stable_semver(m.group(1) or m.group(2)) < stable_semver(version)), len(text))
    newline = "\r\n" if "\r\n" in text else "\n"
    prefix = text[:at]
    separator = "" if prefix.endswith(newline * 2) else (newline if prefix.endswith(newline) else newline * 2)
    return prefix + separator + excerpt.strip().replace("\r\n", "\n").replace("\n", newline) + newline * 2 + text[at:]


def require_material(repo, version, published, ref):
    name = f"changes/{version}"
    expected = git(repo, "rev-parse", f"{published}:{name}").stdout.strip()
    actual = git(repo, "rev-parse", f"{ref}:{name}", check=False)
    notes = git(repo, "show", f"{ref}:CHANGELOG.md", check=False)
    original = git(repo, "show", f"{published}:CHANGELOG.md").stdout
    if actual.returncode or actual.stdout.strip() != expected or notes.returncode:
        raise MDFError("trunk 尚未包含本次发布材料", code="changelog_sync_required")
    try:
        same = section(notes.stdout, version) == section(original, version)
    except MDFError:
        same = False
    if not same:
        raise MDFError("trunk 尚未包含本次 CHANGELOG 条目", code="changelog_sync_required")


def require_synced(repo, version, published):
    trunk, _, settings = sync_policy(repo, version)
    ref = f"refs/remotes/origin/{trunk}"
    if settings["mode"] != "pr":
        return
    path = state_path(repo, version)
    data = read_json(path) if path.is_file() else {}
    if data.get("published_head") != published or not data.get("completed"):
        raise MDFError("先完成 sync-changelog 的 PR、CI 与清理", code="changelog_sync_required")
    git(repo, "fetch", "--no-tags", "origin", f"+refs/heads/{trunk}:{ref}")
    require_material(repo, version, published, ref)


def require_sync_diff(repo, base, head, version):
    """CI 可独立检查精确版本范围，不依赖本地回执。"""
    from mdf_core.workspace.merge_policy import paths, commit_paths, ancestor
    allowed = lambda p: p == "CHANGELOG.md" or p.startswith(f"changes/{version}/")
    changed = paths(repo, base, head)
    for commit in git(repo, "rev-list", f"{base}..{head}").stdout.split():
        parents = git(repo, "show", "-s", "--format=%P", commit).stdout.split()
        if len(parents) == 2 and ancestor(repo, parents[1], base):
            changed += paths(repo, parents[1], commit)
        else:
            changed += commit_paths(repo, commit)
    outside = sorted({p for p in changed if not allowed(p)})
    if outside:
        raise MDFError("发布记录 PR 只能修改本版 changes 与 CHANGELOG", code="pm_paths_forbidden", details={"paths": outside})
    from mdf_core.lifecycle.closeout_render import require_tag_content
    published = require_tag_content(repo, version)["head"]
    identity = git(repo, "show", f"{published}:changes/{version}/delivery.json", check=False)
    try:
        data = json.loads(identity.stdout)
    except ValueError:
        data = {}
    if (not isinstance(data, dict) or not str(data.get("branch", "")).startswith("hotfix/")
            or not str(data.get("base_branch", "")).startswith("support/") or data.get("version") != version):
        raise MDFError("发布记录 PR 必须来源于 support hotfix", code="pm_paths_forbidden", details={"paths": []})
    require_material(repo, version, published, head)
    modes = [git(repo, "ls-tree", ref, "--", "CHANGELOG.md").stdout.split()[0] for ref in (base, head)]
    if modes[0] not in {"100644", "100755"} or modes[0] != modes[1]:
        raise MDFError("发布记录 PR 不得改变 CHANGELOG 文件类型或权限", code="pm_paths_forbidden", details={"paths": ["CHANGELOG.md"]})
    before = blob_text(repo, base, "CHANGELOG.md")
    after = blob_text(repo, head, "CHANGELOG.md")
    expected = insert_section(before, version, section(git(repo, "show", f"{published}:CHANGELOG.md").stdout, version))
    if after != expected:
        raise MDFError("发布记录 PR 改动了其他 CHANGELOG 内容", code="pm_paths_forbidden", details={"paths": ["CHANGELOG.md"]})


def prepare(repo, source, version, record, policy):
    published = published_head(repo, version)
    if published != record["merge_commit"]:
        raise MDFError("final tag 与 support merge 不符", code="tag_conflict")
    path = state_path(repo, version)
    data = read_json(path) if path.is_file() else {}
    branch = PREFIX + version
    work = sibling_worktree(repo, branch)
    trunk, policy_ref, settings = policy
    if data and (data.get("source") != source or data.get("published_head") != published):
        raise MDFError("发布记录同步身份发生变化", code="pull_state_changed")
    if data.get("completed"):
        require_synced(repo, version, published)
        return {"completed": True, "next_intent": "close-out"}
    if not data:
        if local_head(repo, branch) or work.exists() or git(repo, "ls-remote", "origin", f"refs/heads/{branch}").stdout.strip():
            raise MDFError("同步分支或 worktree 已被占用", code="pull_state_changed")
        base = policy_ref
        data = {"source": source, "version": version, "published_head": published, "base": base, "branch": branch,
                "target": trunk, "settings": settings}
        write_json(path, data)
    if local_head(repo, branch) is None:
        # 已准备过的分支可能已由 PR 收口删除；此时交给 complete 核验平台。
        if data.get("prepared"):
            return {"completed": False, "source": branch, "worktree": str(work), "next_intent": "sync-changelog"}
        git(repo, "branch", branch, data["base"])
    occupant = worktree_map(repo).get(branch)
    if occupant is None:
        if work.exists():
            raise MDFError("同步 worktree 路径已被占用", code="pull_state_changed")
        work.parent.mkdir(parents=True, exist_ok=True)
        git(repo, "worktree", "add", str(work), branch)
    elif occupant != work:
        raise MDFError("同步分支被其他 worktree 占用", code="pull_state_changed")
    ensure_clean(work)
    from mdf_core.foundation.paths import ensure_safe_managed_paths
    ensure_safe_managed_paths(work)
    if not (work / "CHANGELOG.md").is_file():
        raise MDFError("CHANGELOG 必须是普通文件", code="invalid_changelog")
    if not data.get("prepared"):
        directory = f"changes/{version}"
        existing = git(work, "rev-parse", f"HEAD:{directory}", check=False)
        expected = git(repo, "rev-parse", f"{published}:{directory}").stdout.strip()
        if not existing.returncode and existing.stdout.strip() != expected:
            raise MDFError("trunk 已有不同的本版材料", code="changelog_conflict")
        text = (work / "CHANGELOG.md").read_bytes().decode("utf-8")
        excerpt = section(git(repo, "show", f"{published}:CHANGELOG.md").stdout, version)
        updated = insert_section(text, version, excerpt)
        git(work, "restore", "--source", published, "--staged", "--worktree", "--", directory)
        (work / "CHANGELOG.md").write_bytes(updated.encode("utf-8"))
        git(work, "add", "--", "CHANGELOG.md")
        if git(work, "diff", "--cached", "--quiet", check=False).returncode:
            git(work, "commit", "-m", f"docs(changelog): 汇总 {version} patch 发布记录")
        data["prepared"] = True
        write_json(path, data)
    return {"completed": False, "source": branch, "worktree": str(work), "target": trunk, "next_intent": "pr"}


def complete(repo, version, record):
    from mdf_core.lifecycle.pull_finish import Forge, origin, lookup_pull, verified_merge
    path = state_path(repo, version)
    data = read_json(path)
    _, _, settings = sync_policy(repo, version)
    forge = Forge(repo, origin(repo, settings["provider"]))
    git(repo, "fetch", "origin", "--prune")
    pull, target = lookup_pull(repo, forge, data["branch"])
    if pull is None or pull["state"] != "merged":
        raise MDFError("发布记录 PR 尚未合入", code="pr_not_merged")
    merged = verified_merge(repo, pull, data["branch"], target, pull["head"])
    published = published_head(repo, version)
    if published != record["merge_commit"] or data["published_head"] != published:
        raise MDFError("发布来源已变化", code="tag_conflict")
    require_sync_diff(repo, f"{merged}^1", merged, version)
    require_material(repo, version, published, f"refs/remotes/origin/{target}")
    if local_head(repo, data["branch"]) or sibling_worktree(repo, data["branch"]).exists():
        raise MDFError("先清理已完成的 pm 分支与 worktree", code="changelog_cleanup_required")
    if git(repo, "ls-remote", "origin", f"refs/heads/{data['branch']}").stdout.strip():
        raise MDFError("先清理远端 pm 分支", code="changelog_cleanup_required")
    write_json(path, {**data, "completed": True, "pull": pull["id"], "merge_commit": merged})
    return {"completed": True, "next_intent": "close-out"}


def command_sync_changelog(args):
    from mdf_core.lifecycle.publish import support_merge_record, require_support_merge
    from mdf_core.lifecycle.pull_finish import finish_lock
    repo = repo_path(args.repo)
    require_git_root(repo)
    if not is_github_flow(repo):
        raise MDFError("sync-changelog 仅用于 github-flow + PR 的 support hotfix", code="invalid_workflow")
    source = args.source or current_branch(repo)
    with finish_lock(repo):
        receipt = support_merge_record(repo, source, args.version)
        if receipt is None:
            raise MDFError("先合入 support hotfix", code="merge_required")
        version, record = receipt
        require_support_merge(repo, record)
        if record.get("closed"):
            if published_head(repo, version) != record["merge_commit"]:
                raise MDFError("final tag 与已完成交付不符", code="tag_conflict")
            result = {"completed": True, "next_intent": None}
        else:
            policy = sync_policy(repo, version)
            if policy[2]["mode"] != "pr":
                raise MDFError("sync-changelog 需要 PR mode 或在途同步记录", code="invalid_workflow")
            result = complete(repo, version, record) if args.complete else prepare(repo, source, version, record, policy)

    emit({"ok": True, "operation": "sync-changelog", **result})
