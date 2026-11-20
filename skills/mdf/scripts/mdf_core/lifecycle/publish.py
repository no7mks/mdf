"""从目标分支第一父链定位实际 no-ff merge commit。"""
from mdf_core.workspace.merge_policy import git


def find_merge(repo, target, head):
    """沿目标第一父链寻找以固定源提交为第二父的双亲 merge。"""
    rows = git(repo, "rev-list", "--first-parent", "--merges", "--parents", target).stdout.splitlines()
    return next((parts[0] for row in rows if len(parts := row.split()) == 3 and parts[2] == head), None)


def merge_record_path(repo, source, version=None):
    from mdf_core.workspace.squash import common_dir
    return common_dir(repo) / "mdf/merge" / source / ((version or "unversioned") + ".json")


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
