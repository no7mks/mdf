"""从目标分支第一父链定位实际 no-ff merge commit。"""
from mdf_core.workspace.merge_policy import git


def find_merge(repo, target, head):
    """沿目标第一父链寻找以固定源提交为第二父的双亲 merge。"""
    rows = git(repo, "rev-list", "--first-parent", "--merges", "--parents", target).stdout.splitlines()
    return next((parts[0] for row in rows if len(parts := row.split()) == 3 and parts[2] == head), None)


def merge_record_path(repo, source, version=None):
    from mdf_core.workspace.squash import common_dir
    return common_dir(repo) / "mdf/merge" / source / ((version or "unversioned") + ".json")
