"""Strict Gitflow branch creation and closeout operations."""

from __future__ import annotations

from pathlib import Path

from .errors import MDFError, emit
from .gitutil import (
    branch_details,
    current_branch,
    ensure_clean,
    repo_path,
    require_git_root,
    run,
)
from .textutil import slugify, stable_semver


ORIGIN = "origin"


def _git(repo: Path, *args: str, check: bool = True):
    return run(["git", *args], cwd=repo, check=check)


def _fetch(repo: Path) -> None:
    result = _git(repo, "remote", "get-url", ORIGIN, check=False)
    if result.returncode:
        raise MDFError("Gitflow requires remote origin", code="missing_origin")
    _git(repo, "fetch", ORIGIN, "--prune")


def _exists(repo: Path, ref: str) -> bool:
    return not _git(repo, "rev-parse", "--verify", "--quiet", ref,
                    check=False).returncode


def _synced(repo: Path, branch: str) -> None:
    local = f"refs/heads/{branch}"
    remote = f"refs/remotes/{ORIGIN}/{branch}"
    if not _exists(repo, local) or not _exists(repo, remote):
        raise MDFError(
            f"Branch {branch} and {ORIGIN}/{branch} must both exist",
            code="missing_upstream_branch",
        )
    left = _git(repo, "rev-parse", local).stdout.strip()
    right = _git(repo, "rev-parse", remote).stdout.strip()
    if left != right:
        raise MDFError(
            f"Branch {branch} must exactly match {ORIGIN}/{branch}",
            code="upstream_diverged",
        )


def default_branch(repo: Path) -> str | None:
    ref = _git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD",
               check=False)
    if ref.returncode:
        return None
    prefix = f"refs/remotes/{ORIGIN}/"
    value = ref.stdout.strip()
    return value.removeprefix(prefix) if value.startswith(prefix) else None


def require_master_default(repo: Path) -> None:
    branch = default_branch(repo)
    if branch == "main":
        raise MDFError(
            "Repository default branch is main; rename it to master first",
            code="main_default_branch",
        )
    if branch is not None and branch != "master":
        raise MDFError(
            f"Repository default branch must be master, got {branch}",
            code="invalid_default_branch",
        )


def _target(kind: str) -> str:
    return "develop" if kind in {"feature", "bugfix", "release"} else "master"


def command_start(args) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_clean(repo)
    _fetch(repo)
    require_master_default(repo)
    base = _target(args.kind)
    _synced(repo, base)
    if args.kind in {"feature", "bugfix"}:
        if not args.name:
            raise MDFError(
                "feature and bugfix require --name", code="missing_name"
            )
        suffix = slugify(args.name)
    else:
        if stable_semver(args.version or "") is None:
            raise MDFError("release and hotfix require stable --version",
                           code="invalid_version")
        suffix = args.version
    branch = f"{args.kind}/{suffix}"
    if _exists(repo, f"refs/heads/{branch}") or _exists(
        repo, f"refs/remotes/{ORIGIN}/{branch}"
    ):
        raise MDFError(f"Branch already exists: {branch}", code="branch_exists")
    objectives = None
    if args.kind == "feature":
        from .proposals import require_startable
        from .delivery_state import safe
        if not args.proposal or not args.objectives_file:
            raise MDFError("feature 需要 --proposal 与 --objectives-file", code="missing_proposal")
        objectives = Path(args.objectives_file).read_text(encoding="utf-8")
        from .constants import MARKER_RE
        if not objectives.strip() or MARKER_RE.search(objectives):
            raise MDFError("objectives 不能为空", code="missing_objectives")
        target = safe(repo, repo / "docs/specs" / suffix)
        if target.exists() or (repo / "docs/changes/unreleased" / suffix).exists():
            raise MDFError("交付 slug 已存在", code="collision")
        _git(repo, "checkout", base)
        require_startable(repo, args.proposal)
    else:
        _git(repo, "checkout", base)
    start_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-b", branch)
    if objectives is not None:
        from .delivery_state import write_json
        target.mkdir(parents=True)
        (target / "objectives.md").write_text(objectives, encoding="utf-8")
        write_json(target / "delivery.json", {"proposal": args.proposal, "slug": suffix,
                   "branch": branch, "start_commit": start_commit})
        _git(repo, "add", "--", str(target.relative_to(repo)))
        _git(repo, "commit", "-m", f"docs(delivery): 确认 {args.proposal} 交付目标")
    pushed = _git(repo, "push", "-u", ORIGIN, branch, check=False)
    if pushed.returncode:
        raise MDFError(
            "本地分支已创建，但推送失败；保留现场，核对远端后再决定补推或处理",
            code="start_push_failed",
            details={
                "branch": branch,
                "base": base,
                "local_head": _git(repo, "rev-parse", "HEAD").stdout.strip(),
                "remote_state": "unknown",
                "stderr": pushed.stderr,
            },
        )
    emit({"ok": True, "operation": "start", "branch": branch,
          "base": base, "start_commit": start_commit, "upstream": f"{ORIGIN}/{branch}"})


def _merge(repo: Path, source: str, target: str, before_commit=None) -> None:
    _git(repo, "checkout", target)
    result = _git(repo, "merge", "--no-ff", "--no-commit", source, check=False)
    if result.returncode:
        _git(repo, "merge", "--abort", check=False)
        raise MDFError(
            f"Merge conflict: {source} -> {target}; merge was aborted",
            code="merge_conflict",
        )
    if before_commit is not None:
        before_commit()
    message = f"chore(gitflow): 合并 {source} 到 {target}"
    _git(repo, "commit", "-m", message)


def command_finish_gitflow(args) -> None:
    repo = repo_path(args.repo)
    require_git_root(repo)
    ensure_clean(repo)
    source = current_branch(repo)
    details = branch_details(source)
    if not details["supported"]:
        raise MDFError("finish requires a Gitflow delivery branch",
                       code="unsupported_branch")
    kind = details["kind"]
    _fetch(repo)
    require_master_default(repo)
    _synced(repo, source)
    targets = (
        ["develop"]
        if kind in {"feature", "bugfix"}
        else ["master", "develop"]
    )
    for target in targets:
        _synced(repo, target)
    complete_feature = None
    if kind == "feature":
        from .delivery_state import locate, require_finish
        from .proposals import records
        from .prp_split import render
        root, data = locate(repo)
        require_finish(repo, root, data)
        change = repo / "docs/changes/unreleased" / data["slug"] / "CHANGE.md"
        if root.parent != repo / "docs/changes/unreleased" or not change.is_file():
            raise MDFError("finish 前必须将材料归入 Change", code="missing_change")
        from .yamlutil import read_frontmatter
        meta, _ = read_frontmatter(change)
        if meta.get("proposals") != [data["proposal"]] or meta.get("source_branch") != source:
            raise MDFError("Change 必须对应本 feature 的唯一 PRP", code="invalid_change")
        path, proposal, body = records(repo)[data["proposal"]]
        if proposal["status"] != "ready":
            raise MDFError("交付 PRP 状态不正确", code="invalid_proposal")
        def complete_feature():
            # Only a successful merge to develop can mark the result implemented.
            merged, merged_body = read_frontmatter(path)
            path.write_text(render({**merged, "status": "implemented"}, merged_body))
            _git(repo, "add", "--", str(path.relative_to(repo)))
    if kind in {"feature", "bugfix"}:
        _merge(repo, source, "develop", complete_feature)
        refs = ["develop", f":{source}"]
    else:
        _merge(repo, source, "master")
        version = details["version"]
        assert isinstance(version, str)
        tag = f"v{version}"
        if _exists(repo, f"refs/tags/{tag}") or _exists(
            repo, f"refs/tags/{ORIGIN}/{tag}"
        ):
            raise MDFError(f"Tag already exists: {tag}", code="tag_exists")
        _git(repo, "tag", "-a", tag, "-m", f"chore(release): 发布 {tag}")
        _merge(repo, "master", "develop")
        refs = ["master", "develop", f"refs/tags/{tag}", f":{source}"]
    _git(repo, "push", "--atomic", ORIGIN, *refs)
    _git(repo, "branch", "-d", source)
    tag = f"v{details['version']}" if kind in {"release", "hotfix"} else None
    emit(
        {
            "ok": True,
            "operation": "finish-gitflow",
            "source": source,
            "targets": targets,
            "deleted": source,
            "tag": tag,
        }
    )
