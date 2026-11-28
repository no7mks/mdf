"""混合流程版本记录的来源、发布线与外部 tag 校验。"""
import re

from mdf_core.foundation.errors import MDFError, add_finding
from mdf_core.foundation.textutil import stable_semver
from mdf_core.workspace.merge_policy import ancestor, git, sha
from mdf_core.workspace.workflow_policy import trunk_branch


def release_line(repo, metadata):
    line = metadata.get("release_line")
    if line != trunk_branch(repo) and not re.fullmatch(r"support/(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", str(line)):
        raise MDFError("release_line 必须是当前 trunk 或 support/<major.minor>", code="invalid_release_line")
    version = stable_semver(metadata.get("version"))
    if str(line).startswith("support/") and (version is None or line != f"support/{version[0]}.{version[1]}"):
        raise MDFError("版本与 support 发布线不符", code="invalid_release_line")
    return line


def line_ref(repo, line):
    for ref in (f"refs/heads/{line}", f"refs/remotes/origin/{line}"):
        if not git(repo, "rev-parse", "--verify", ref, check=False).returncode:
            return ref
    raise MDFError("缺少声明的发布线历史", code="missing_release_line")


def historical_head(repo, metadata):
    head = metadata.get("release_commit")
    if not re.fullmatch(r"[0-9a-f]{40}", str(head)) or sha(repo, head) != head:
        raise MDFError("release_commit 必须为完整 commit SHA", code="invalid_release_commit")
    if not ancestor(repo, head, line_ref(repo, release_line(repo, metadata))):
        raise MDFError("release_commit 不属于声明的发布线", code="invalid_release_commit")
    tag = metadata.get("release_tag")
    if tag is not None and (not isinstance(tag, str) or not tag or sha(repo, f"refs/tags/{tag}") != head):
        raise MDFError("外部 release_tag 与 release_commit 不符", code="tag_conflict")
    previous = metadata.get("previous_version")
    if previous not in (None, "none"):
        if stable_semver(previous) is None or stable_semver(previous) >= stable_semver(metadata.get("version")):
            raise MDFError("历史版本基线须严格早于目标版本", code="invalid_release_history")
        if not ancestor(repo, f"refs/tags/v{previous}^{{commit}}", head):
            raise MDFError("历史版本基线不在本发布线历史中", code="invalid_release_history")
    return head


def validate_record_mode(repo, metadata, root, rel, findings):
    mode = metadata.get("record_mode", "standard")
    if mode not in ("standard", "ledgerless", "post_hoc") or (not root and mode != "standard"):
        add_finding(findings, "change.record_mode", "record_mode 仅用于版本根，须为 standard、ledgerless 或 post_hoc", rel)
        return
    try:
        if mode == "standard":
            if any(key in metadata for key in ("release_commit", "release_tag", "release_line")):
                raise MDFError("standard 版本不使用外部发布字段", code="invalid_release_record")
        else:
            release_line(repo, metadata)
            if mode == "post_hoc":
                historical_head(repo, metadata)
            elif any(key in metadata for key in ("release_commit", "release_tag")):
                raise MDFError("ledgerless 版本不使用历史 commit/tag 字段", code="invalid_release_record")
    except (MDFError, TypeError, ValueError) as exc:
        add_finding(findings, "change.release_record", str(exc), rel)
