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


def _tag_lines(repo: Path) -> dict[tuple[int, int], tuple[int, int, int]]:
    lines: dict[tuple[int, int], tuple[int, int, int]] = {}
    for tag in _git(repo, "tag", "--list", "v*").stdout.split():
        version = stable_semver(tag[1:])
        if version is not None:
            key = version[:2]
            lines[key] = max(lines.get(key, version), version)
    return lines


def _support_keys(repo: Path) -> set[tuple[int, int]]:
    shown = _git(repo, "for-each-ref", "--format=%(refname:short)",
                 "refs/heads/support/*", "refs/remotes/origin/support/*", check=False)
    keys = set()
    for name in shown.stdout.split():
        short = name.removeprefix("origin/")
        match = re.fullmatch(r"support/(\d+)\.(\d+)", short)
        if match:
            keys.add((int(match.group(1)), int(match.group(2))))
    return keys


def release_lines(repo: Path) -> dict[tuple[int, int], tuple[int, int, int]]:
    """已发布 tag 与已有 support/* 合并后的版本线；无 tag 的 support 线补 0 patch。"""
    lines = _tag_lines(repo)
    for key in _support_keys(repo):
        lines.setdefault(key, (*key, 0))
    return lines


def _no_tags(repo: Path) -> MDFError:
    return MDFError("没有任何发布 tag；请改走 bugfix/* 合入 trunk", code="missing_release_tag")


def hotfix_base(repo: Path, args) -> tuple[str, dict[str, Any] | None]:
    """已有发布 tag 时 hotfix 一律走 support/<major.minor>；单线可省略 --support。"""
    wanted = getattr(args, "support", None)
    if not _tag_lines(repo):
        raise _no_tags(repo)
    lines = release_lines(repo)
    if wanted is None:
        if len(lines) != 1:
            raise MDFError("存在多条已发布版本线，hotfix 须显式传 --support <major.minor>",
                           code="support_required",
                           details={"lines": sorted(f"{a}.{b}" for a, b in lines)})
        major, minor = next(iter(lines))
        wanted = f"{major}.{minor}"
    if not EPOCH_RE.match(wanted):
        raise MDFError("--support 必须为 <major>.<minor>", code="invalid_support")
    key = tuple(int(part) for part in wanted.split("."))
    tagged = _tag_lines(repo)
    if key not in tagged:
        raise MDFError(f"没有 v{wanted}.* 发布 tag，不能建立 support/{wanted}", code="missing_release_tag")
    version = getattr(args, "version", None)
    if version is not None and (stable_semver(version) or ())[:2] != key:
        raise MDFError("hotfix 版本必须属于 --support 指定的版本线", code="version_line_mismatch")
    branch = support_branch(wanted)
    exists = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0
    tag = "v" + ".".join(str(part) for part in tagged[key])
    return branch, {"major_minor": wanted, "branch": branch, "create_from": None if exists else tag}


def _align_latest_release(text: str, version: str) -> str:
    lines = [f'  latest_release: "{version}"' if line.startswith("  latest_release:") else line
             for line in text.splitlines()]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def ensure_support_branch(repo: Path, support: dict[str, Any], trunk: str) -> None:
    """远端已有同名分支则追踪；否则从 tag 切出，并同步 workflow、closeout 与 latest_release。"""
    from mdf_core.workspace.merge_policy import configured
    branch, tag = support["branch"], support["create_from"]
    if _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0:
        return
    remote = f"refs/remotes/origin/{branch}"
    if _git(repo, "rev-parse", "--verify", "--quiet", remote, check=False).returncode == 0:
        _git(repo, "branch", "--track", branch, remote)
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
            if isinstance(tag, str) and tag.startswith("v"):
                text = _align_latest_release(text, tag[1:])
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


def _require_open_trunk_bug(repo: Path, trunk: str, bug_id: str) -> None:
    from mdf_core.foundation.constants import OBJECT_FILE_RE
    from mdf_core.foundation.yamlutil import frontmatter_span, parse_yaml
    ref = f"refs/heads/{trunk}"
    listed = _git(repo, "ls-tree", "-r", "--name-only", ref, "--", "docs/bugs", check=False).stdout.splitlines()
    found = [rel for rel in listed if (match := OBJECT_FILE_RE.fullmatch(Path(rel).name))
             and match.group(1) == bug_id and Path(rel).parts[:2] == ("docs", "bugs")]
    if len(found) != 1:
        raise MDFError(f"{trunk} 上缺少 Bug {bug_id}", code="trunk_first_required", details={"bug_id": bug_id})
    shown = _git(repo, "show", f"{ref}:{found[0]}").stdout
    start, end, _body = frontmatter_span(shown)
    status = parse_yaml(shown[start:end]).get("status")
    if status != "open":
        raise MDFError(f"{trunk} 上的 Bug {bug_id} 不是 open", code="trunk_first_required",
                       details={"bug_id": bug_id, "status": status})


def forbid_bug_edits(repo: Path, source: str) -> None:
    """support/* 及其 hotfix 不得增删改 docs/bugs/bug-*.md。"""
    from mdf_core.workspace.gitutil import branch_details
    details = branch_details(source)
    base = None
    if source.startswith("support/"):
        trunk = trunk_branch(repo)
        base = _git(repo, "merge-base", f"refs/heads/{trunk}", source).stdout.strip()
    if details["kind"] == "hotfix":
        from mdf_core.lifecycle.hotfix_version import delivery_record
        record = delivery_record(repo, source, ref=f"refs/heads/{source}")
        recorded = record[1].get("base_branch") if record else None
        base = recorded if isinstance(recorded, str) and recorded.startswith("support/") else None
    if base is None:
        return
    diff = _git(repo, "diff", "--name-only", f"{base}...{source}", "--", "docs/bugs", check=False)
    changed = [name for name in diff.stdout.splitlines() if Path(name).name.startswith("bug-") and name.endswith(".md")]
    if changed:
        raise MDFError("维护线不得增删改 docs/bugs 下的 Bug 真源", code="bug_source_forbidden",
                       details={"paths": changed})


def recheck_before_publish(repo: Path, source: str, version: str) -> None:
    """发布前再次核验 urgent_support_first 的 trunk Bug 仍为 open。"""
    from mdf_core.workspace.workflow_policy import is_github_flow
    if not is_github_flow(repo):
        return
    from mdf_core.lifecycle.late_decision import target_for
    target = target_for(repo, source)
    if not is_support_branch(str(target)):
        return
    from mdf_core.foundation.yamlutil import read_frontmatter
    from mdf_core.workspace.gitutil import branch_details, unreleased_slug
    folder = unreleased_slug(branch_details(source))
    path = repo / "changes" / "unreleased" / folder / "CHANGE.md"
    if not path.is_file():
        path = repo / "changes" / version / "CHANGE.md"
    if not path.is_file():
        return
    metadata, _body = read_frontmatter(path)
    fixes = metadata.get("trunk_fixes")
    if isinstance(fixes, list) and fixes:
        verify_trunk_first(repo, fixes, version)


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
        if disposition == "urgent_support_first":
            _require_open_trunk_bug(repo, trunk, item["bug_id"])
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
