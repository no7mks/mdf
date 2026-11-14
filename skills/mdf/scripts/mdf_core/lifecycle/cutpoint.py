"""github-flow 的历史切点 release：固定 SHA 冻结，不随 trunk 前进。"""

from __future__ import annotations

from pathlib import Path

from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.textutil import stable_semver
from mdf_core.workspace.gitutil import run
from mdf_core.workspace.workflow_policy import manifest_at


def _git(repo: Path, *args: str, check: bool = True):
    return run(["git", *args], cwd=repo, check=check)


def resolve_cutpoint(repo: Path, raw: str, trunk: str) -> str:
    """校验 --from-commit：位于 trunk 第一父链；上一发布 tag（若有）须是切点的 ancestor。"""
    resolved = _git(repo, "rev-parse", "--verify", "--quiet", f"{raw}^{{commit}}", check=False)
    if resolved.returncode:
        raise MDFError(f"无法解析 --from-commit：{raw}", code="invalid_cutpoint")
    commit = resolved.stdout.strip()
    first_parent = _git(repo, "rev-list", "--first-parent", f"refs/heads/{trunk}").stdout.split()
    if commit not in first_parent:
        raise MDFError(f"切点必须位于 {trunk} 的第一父链", code="cutpoint_not_on_trunk",
                       details={"commit": commit, "trunk": trunk})
    latest = (manifest_at(repo, f"refs/heads/{trunk}").get("versioning") or {}).get("latest_release")
    if latest is not None:
        if stable_semver(latest) is None:
            raise MDFError("trunk 的 latest_release 不是稳定 SemVer", code="invalid_cutpoint")
        tag = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/v{latest}^{{commit}}", check=False)
        if tag.returncode:
            raise MDFError(f"缺少上一发布 tag v{latest}", code="missing_release_tag")
        if _git(repo, "merge-base", "--is-ancestor", tag.stdout.strip(), commit, check=False).returncode:
            raise MDFError(f"上一发布 tag v{latest} 不是切点的 ancestor", code="cutpoint_before_latest_release",
                           details={"commit": commit, "latest_release": latest})
    return commit


def require_not_frozen_catch_up(identity: dict, repo: Path, incoming: str) -> None:
    """frozen_cutpoint 的 release/* 禁止 catch-up 引入切点之后的 trunk 提交。"""
    if identity.get("frozen_cutpoint") is not True:
        return
    if _git(repo, "merge-base", "--is-ancestor", incoming, "HEAD", check=False).returncode == 0:
        return
    raise MDFError("release 已冻结在历史切点，禁止 catch-up 合入后续 trunk 提交；"
                   "冲突与对齐经集成分支处理", code="frozen_cutpoint",
                   details={"cutpoint_commit": identity.get("cutpoint_commit")})
