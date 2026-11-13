"""github-flow 的 `support/<major.minor>` 维护线：惰性切出、配置同步与 Trunk-First 记录。"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from mdf_core.foundation.constants import EPOCH_RE
from mdf_core.foundation.errors import MDFError
from mdf_core.foundation.paths import manifest_path
from mdf_core.foundation.textutil import stable_semver
from mdf_core.workspace.gitutil import run
from mdf_core.workspace.workflow_policy import (
    render_closeout_lines,
    render_workflow_lines,
    set_manifest_block,
    support_branch,
    trunk_branch,
    workflow_config,
)

DISPOSITIONS = ("backported", "trunk_not_affected", "urgent_support_first")
NEEDS_REASON = ("trunk_not_affected", "urgent_support_first")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _git(repo: Path, *args: str, check: bool = True):
    return run(["git", *args], cwd=repo, check=check)


def release_lines(repo: Path) -> dict[tuple[int, int], tuple[int, int, int]]:
    """已发布的 <major>.<minor> 线及各线最大稳定版本；按本仓全部 v* tag 计算。"""
    lines: dict[tuple[int, int], tuple[int, int, int]] = {}
    for tag in _git(repo, "tag", "--list", "v*").stdout.split():
        version = stable_semver(tag[1:])
        if version is not None:
            key = version[:2]
            lines[key] = max(lines.get(key, version), version)
    return lines


def hotfix_base(repo: Path, args) -> tuple[str, dict[str, Any] | None]:
    """github-flow 的 hotfix 基线：单线从 trunk，多线须显式 --support；支持线不存在时标记惰性切出。"""
    trunk = trunk_branch(repo)
    wanted = getattr(args, "support", None)
    lines = release_lines(repo)
    if wanted is None:
        if len(lines) > 1:
            raise MDFError("存在多条已发布版本线，hotfix 须显式传 --support <major.minor>",
                           code="support_required",
                           details={"lines": sorted(f"{a}.{b}" for a, b in lines)})
        return trunk, None
    if not EPOCH_RE.match(wanted):
        raise MDFError("--support 必须为 <major>.<minor>", code="invalid_support")
    key = tuple(int(part) for part in wanted.split("."))
    if key not in lines:
        raise MDFError(f"没有 v{wanted}.* 发布 tag，不能建立 support/{wanted}", code="missing_release_tag")
    version = getattr(args, "version", None)
    if version is not None and (stable_semver(version) or ())[:2] != key:
        raise MDFError("hotfix 版本必须属于 --support 指定的版本线", code="version_line_mismatch")
    branch = support_branch(wanted)
    exists = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0
    tag = "v" + ".".join(str(part) for part in lines[key])
    return branch, {"major_minor": wanted, "branch": branch, "create_from": None if exists else tag}


def ensure_support_branch(repo: Path, support: dict[str, Any], trunk: str) -> None:
    """从该线最新 tag 切出 support 分支，并把当前 trunk 的 workflow 与 closeout 配置写入后提交。"""
    from mdf_core.workspace.merge_policy import configured
    branch, tag = support["branch"], support["create_from"]
    if _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0:
        return
    _git(repo, "branch", branch, f"refs/tags/{tag}^{{commit}}")
    workflow = workflow_config(repo, f"refs/heads/{trunk}")
    closeout = configured(repo, f"refs/heads/{trunk}")
    with tempfile.TemporaryDirectory(prefix="mdf-support-") as temp:
        work = Path(temp) / "work"
        _git(repo, "worktree", "add", str(work), branch)
        try:
            path = manifest_path(work)
            text = set_manifest_block(path.read_text(encoding="utf-8"), "workflow", render_workflow_lines(workflow))
            text = set_manifest_block(text, "closeout", render_closeout_lines(closeout), before="baselines:")
            path.write_text(text, encoding="utf-8")
            _git(work, "add", "--", ".mdf/manifest.yaml")
            if _git(work, "diff", "--cached", "--quiet", check=False).returncode:
                _git(work, "commit", "-m", f"chore(support): 同步 {trunk} 的 workflow 与 closeout 配置")
        finally:
            _git(repo, "worktree", "remove", "--force", str(work), check=False)


def is_support_branch(branch: str) -> bool:
    return branch.startswith("support/")


def normalize_trunk_fixes(raw: Any, fixed: list[str]) -> list[dict[str, str]]:
    """校验 hotfix 的 trunk_fixes：每个 fixed Bug 必须有且仅有一条处置；不碰 Git。"""
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise MDFError("hotfix trunk_fixes 必须是列表", code="invalid_closeout_spec")
    result: list[dict[str, str]] = []
    for item in raw:
        if (not isinstance(item, dict) or set(item) - {"bug_id", "trunk_disposition", "source_commit", "reason"}
                or "bug_id" not in item or "trunk_disposition" not in item
                or any(not isinstance(value, str) for value in item.values())):
            raise MDFError("trunk_fixes 项只允许 bug_id、trunk_disposition、source_commit、reason",
                           code="invalid_closeout_spec")
        result.append(dict(item))
    ids = [item["bug_id"] for item in result]
    if len(ids) != len(set(ids)):
        raise MDFError("trunk_fixes 的 Bug 不得重复", code="invalid_closeout_spec")
    missing = sorted(set(fixed) - set(ids))
    extra = sorted(set(ids) - set(fixed))
    if missing or extra:
        raise MDFError("trunk_fixes 必须与 fixed 的 Bug 一一对应", code="trunk_first_required",
                       details={"missing": missing, "unexpected": extra})
    return result


def verify_trunk_first(repo: Path, fixes: list[dict[str, str]], version: str) -> list[dict[str, str]]:
    """support 收口门禁：backported 核验 source_commit 在 trunk 可达；例外须附非空 reason。"""
    trunk = trunk_branch(repo)
    checked = []
    for item in fixes:
        disposition = item["trunk_disposition"]
        if disposition not in DISPOSITIONS:
            raise MDFError("trunk_disposition 必须为 backported、trunk_not_affected 或 urgent_support_first",
                           code="trunk_first_required", details={"bug_id": item["bug_id"]})
        if disposition in NEEDS_REASON and not item.get("reason", "").strip():
            raise MDFError(f"{disposition} 须附非空 reason", code="trunk_first_required",
                           details={"bug_id": item["bug_id"]})
        if disposition == "backported":
            commit = item.get("source_commit", "")
            if not SHA_RE.match(commit):
                raise MDFError("backported 须提供 40 位 source_commit", code="trunk_first_required",
                               details={"bug_id": item["bug_id"]})
            reachable = _git(repo, "merge-base", "--is-ancestor", commit, f"refs/heads/{trunk}", check=False)
            if reachable.returncode:
                raise MDFError(f"{trunk} 上尚未包含修复提交；默认须 Trunk-First", code="trunk_first_required",
                               details={"bug_id": item["bug_id"], "source_commit": commit})
        checked.append({**item, "released_in": version})
    return checked


def render_trunk_fixes(fixes: list[dict[str, str]]) -> str:
    import json
    if not fixes:
        return ""
    lines = ["trunk_fixes:"]
    for item in fixes:
        keys = ["bug_id", "trunk_disposition", "source_commit", "reason", "released_in"]
        first = True
        for key in keys:
            if key in item:
                lines.append(f"  {'- ' if first else '  '}{key}: {json.dumps(item[key], ensure_ascii=False)}")
                first = False
    return "\n".join(lines) + "\n"
