"""从目标分支第一父链定位实际 no-ff merge commit。"""
from mdf_core.workspace.merge_policy import git


def support_merge_record(repo, source, version=None):
    """从本地合并回执恢复 support hotfix，源分支或 tag 可尚未存在。"""
    from mdf_core.foundation.errors import MDFError
    from mdf_core.foundation.textutil import stable_semver
    from mdf_core.lifecycle.delivery_state import read_json
    from mdf_core.lifecycle.hotfix_version import delivery_record
    from mdf_core.lifecycle.support_line import support_hotfix
    from mdf_core.workspace.gitutil import branch_details

    details = branch_details(source)
    if details["kind"] != "hotfix":
        return None
    if version is not None and (stable_semver(version) is None or details["version"] not in (None, version)):
        raise MDFError("指定版本与 hotfix 不匹配", code="invalid_arguments")
    version = version or details["version"]
    folder = merge_record_path(repo, source, version).parent
    candidates = [folder / f"{version}.json"] if version else sorted(folder.glob("*.json"))
    matches = []
    for path in candidates:
        if not path.is_file() or not stable_semver(path.stem):
            continue
        record = read_json(path)
        if record.get("source") != source or not isinstance(record.get("head"), str) or not isinstance(record.get("target"), str):
            continue
        identity = delivery_record(repo, source, ref=record["head"])
        if (identity and identity[1].get("version") == path.stem
                and support_hotfix(repo, source, data=identity[1], target=record["target"])):
            matches.append((path.stem, record))
    if len(matches) > 1:
        raise MDFError("同名 hotfix 存在多个合并回执，请指定 --version", code="invalid_arguments")
    return matches[0] if matches else None


def find_merge(repo, target, head):
    """沿目标第一父链寻找以固定源提交为第二父的双亲 merge。"""
    rows = git(repo, "rev-list", "--first-parent", "--merges", "--parents", target).stdout.splitlines()
    return next((parts[0] for row in rows if len(parts := row.split()) == 3 and parts[2] == head), None)


def merge_record_path(repo, source, version=None):
    from mdf_core.workspace.squash import common_dir
    return common_dir(repo) / "mdf/merge" / source / ((version or "unversioned") + ".json")


def pending_support_publications(repo):
    from mdf_core.lifecycle.delivery_state import read_json
    from mdf_core.workspace.squash import common_dir

    folder = common_dir(repo) / "mdf/merge/hotfix"
    pending = []
    for path in sorted(folder.glob("*/*.json")):
        record = read_json(path)
        if "closed" in record and not record.get("closed") and not record.get("pending"):
            pending.append({"source": record["source"], "version": path.stem})
    return pending


def remote_contains_merge(repo, target, merged):
    """刷新精确远端目标后证明 merge 已实际接纳；不信任旧 tracking ref。"""
    from mdf_core.workspace.merge_policy import ancestor
    ref = f"refs/heads/{target}"
    advertised = git(repo, "ls-remote", "origin", ref).stdout.split()
    if not advertised:
        return False
    tracking = f"refs/remotes/origin/{target}"
    git(repo, "fetch", "--no-tags", "origin", f"+{ref}:{tracking}")
    return ancestor(repo, merged, tracking)


def require_remote_merge(repo, target, merged):
    from mdf_core.foundation.errors import MDFError
    if not remote_contains_merge(repo, target, merged):
        raise MDFError("远端目标尚未包含本次 merge，先续办 merge", code="merge_required")


def require_support_merge(repo, record):
    from mdf_core.foundation.errors import MDFError
    target, merged = record["target"], record["merge_commit"]
    require_remote_merge(repo, target, merged)
    if find_merge(repo, f"refs/remotes/origin/{target}", record["head"]) != merged:
        raise MDFError("support 第一父链不包含本次 merge", code="merge_required")
    return merged
