"""复核固定历史来源与已提交的补账产物，不把完成标记当成验收。"""
from mdf_core.foundation.errors import MDFError
from mdf_core.inspection.validate_reconcile import historical_head
from mdf_core.workspace.changelog_sync import section
from mdf_core.workspace.merge_policy import git, sha


def require_history_source(repo, release):
    historical_head(repo, release)
    for tag_key, oid_key in (("release_tag", "release_tag_oid"), ("previous_tag", "previous_tag_oid")):
        tag = release.get(tag_key)
        if tag:
            actual = git(repo, "rev-parse", "--verify", f"refs/tags/{tag}", check=False)
            if actual.returncode or actual.stdout.strip() != release.get(oid_key):
                raise MDFError("历史 tag 对象已改变，先重新核对发布来源", code="reconcile_state_changed")
    if release.get("previous_tag") and sha(repo, f"refs/tags/{release['previous_tag']}") != release["base"]:
        raise MDFError("历史发布区间的基线已改变", code="reconcile_state_changed")


def require_record(repo, plan, version):
    tree = git(repo, "rev-parse", "--verify", f"HEAD:changes/{version}", check=False)
    try:
        excerpt = section((repo / "CHANGELOG.md").read_text(), version)
    except (OSError, MDFError) as exc:
        raise MDFError("已记录的 CHANGELOG 章节缺失", code="reconcile_state_changed") from exc
    if (tree.returncode or tree.stdout.strip() != plan.get("record_trees", {}).get(version)
            or excerpt != plan.get("record_sections", {}).get(version)):
        raise MDFError("已补账材料被修改；保留现场核对", code="reconcile_state_changed")
    if plan["record_mode"] == "post_hoc":
        release = next(r for r in plan["releases"] if r["version"] == version)
        require_history_source(repo, release)
