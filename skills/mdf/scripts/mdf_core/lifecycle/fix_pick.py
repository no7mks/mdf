"""在 GitHub Flow 开工时冻结已有修复的移植来源。"""

import re

from mdf_core.foundation.constants import EPOCH_RE, OBJECT_ID_RE
from mdf_core.foundation.errors import MDFError
from mdf_core.lifecycle.delivery_state import git, split_objectives_steps
from mdf_core.lifecycle.support_line import SHA_RE, trunk_bug
from mdf_core.workspace.merge_policy import ancestor
from mdf_core.workspace.workflow_policy import support_branch


def _source_tip(repo, branch):
    ref = f"refs/heads/{branch}"
    if git(repo, "remote", "get-url", "origin", check=False).returncode:
        return ref, _local_tip(repo, ref)
    listed = git(repo, "ls-remote", "--exit-code", "origin", ref, check=False)
    if listed.returncode:
        raise MDFError("无法读取 origin 上的修复来源", code="invalid_pick", details={"ref": ref})
    head = listed.stdout.split()[0]
    if git(repo, "cat-file", "-e", f"{head}^{{commit}}", check=False).returncode:
        raise MDFError("本地缺少 origin 来源分支的 commit，请先 fetch", code="invalid_pick", details={"head": head})
    return f"refs/remotes/origin/{branch}", head


def _local_tip(repo, ref):
    resolved = git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    if resolved.returncode:
        raise MDFError("pick 来源分支不存在", code="invalid_pick", details={"ref": ref})
    return resolved.stdout.strip()


def pick_source(repo, args, trunk, *, github):
    commits = getattr(args, "pick_commit", None)
    source = getattr(args, "pick_from", None)
    if commits is None and source is None:
        return None
    if not github or args.kind not in {"bugfix", "hotfix"}:
        raise MDFError("pick 仅适用于 github-flow 的 bugfix 或 hotfix", code="invalid_pick")
    if not commits or len(set(commits)) != len(commits) or any(not SHA_RE.fullmatch(sha) for sha in commits):
        raise MDFError("pick 需要按移植顺序提供互异的完整 commit SHA", code="invalid_pick")

    bug = getattr(args, "bug", None)
    local_trunk = None
    if args.kind == "hotfix":
        if source is not None:
            raise MDFError("hotfix pick 的来源固定为 trunk", code="invalid_pick")
        if not bug or not bug.startswith("bug-") or not OBJECT_ID_RE.fullmatch(bug):
            raise MDFError("hotfix pick 需要 --bug <Bug-ID>", code="invalid_pick")
        ref, head = _source_tip(repo, trunk)
        if trunk_bug(repo, bug, ref=head).get("status") == "rejected":
            raise MDFError("pick 需要 trunk 上有效的 Bug", code="invalid_pick")
        local_trunk = _local_tip(repo, f"refs/heads/{trunk}")
        if local_trunk != head:
            trunk_bug(repo, bug, ref=local_trunk)
    else:
        line = (source or "").removeprefix("support/")
        if not EPOCH_RE.fullmatch(line) or source != support_branch(line):
            raise MDFError("bugfix pick 需要 --pick-from support/<major.minor>", code="invalid_pick")
        ref, head = _source_tip(repo, source)
    for commit in commits:
        # 禁止用 tag 对象 SHA 代替 commit，即使 Git 可以剥离出同一提交。
        if (git(repo, "cat-file", "-t", commit, check=False).stdout.strip() != "commit"
                or not ancestor(repo, commit, head)):
            raise MDFError("pick commit 不在来源分支上", code="invalid_pick",
                           details={"ref": ref, "commit": commit})
        if local_trunk and local_trunk != head and not ancestor(repo, commit, local_trunk):
            raise MDFError("本地 trunk 缺少已共享的修复 commit，请先同步 trunk", code="invalid_pick",
                           details={"commit": commit})
    return {"bug": bug, "source_ref": ref, "source_head": head, "commits": commits}


def pick_objectives(text):
    """只替换步骤清单，保留已确认的目标、约束、验收与准备说明。"""
    before, steps, after = split_objectives_steps(text)
    prose = re.sub(r"(?m)^- \[[ xX]\][ \t]+[^\n]*(?:\n|$)", "", steps).strip("\n")
    start = "- [x] 确认目标与约束（start）"
    pending = ("pick", "lint", "code-review", "verify branch", "fact audit", "catch-up", "consolidate")
    checklist = "\n".join((start, *(f"- [ ] {step}" for step in pending)))
    sections = (before.rstrip("\n"), prose, checklist, after.rstrip("\n"))
    return "\n\n".join(part for part in sections if part) + "\n"
