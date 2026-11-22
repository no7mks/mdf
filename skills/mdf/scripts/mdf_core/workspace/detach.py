"""移除业务仓里已跟踪的 MDF Skill 副本，保留 .mdf/ 与 docs/。"""

from __future__ import annotations

from pathlib import PurePosixPath
import shutil

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.foundation.paths import load_manifest, manifest_path, tool_root
from mdf_core.workspace.agents_block import block_span, render_block
from mdf_core.workspace.gitutil import repo_path, require_git_root, run

HOST_COPIES = (
    ".agents/skills/mdf",
    ".claude/skills/mdf",
    ".codex/skills/mdf",
    ".cursor/skills/mdf",
    ".kiro/skills/mdf",
    ".openclaw/skills/mdf",
)
MESSAGE = "chore(mdf): 移除仓内 MDF Skill 副本"


def _allowed(path: str) -> bool:
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        return False
    if path.startswith((".mdf/", "docs/")) or path in {".mdf", "docs"}:
        return False
    return any(path == root or path.startswith(root + "/") for root in HOST_COPIES)


def _tracked(repo, relative: str) -> list[str]:
    listed = run(["git", "ls-files", "-z", "--", relative], cwd=repo, check=False)
    return [item for item in listed.stdout.split("\0") if item]


def _dirty(repo, relative: str) -> bool:
    status = run(
        ["git", "status", "--porcelain", "--", relative], cwd=repo, check=False,
    )
    return bool(status.stdout.strip())


def _guard(paths: list[str]) -> None:
    if any(not _allowed(path) for path in paths):
        raise MDFError("detach 拒绝删除 Skill 副本以外的路径", code="detach_forbidden_path")


def _agents_plan(repo):
    path = repo / "AGENTS.md"
    if not path.exists():
        return {"path": "AGENTS.md", "action": "skip", "reason": "absent"}, None
    if path.is_symlink() or not path.is_file():
        raise MDFError("AGENTS.md 必须是普通文件", code="detach_agents_not_file")
    if _dirty(repo, "AGENTS.md"):
        raise MDFError("AGENTS.md 有未提交改动", code="detach_dirty")
    current = path.read_text(encoding="utf-8")
    span = block_span(current)
    if span is None or not manifest_path(repo).is_file():
        reason = "no_block" if span is None else "no_manifest"
        return {"path": "AGENTS.md", "action": "skip", "reason": reason}, None
    template = (tool_root() / "assets" / "templates" / "agents-managed-block.md").read_text(
        encoding="utf-8",
    )
    start, end = span
    updated = current[:start] + render_block(template.strip(), load_manifest(repo)) + current[end:]
    if updated == current:
        return {"path": "AGENTS.md", "action": "unchanged"}, None
    return {"path": "AGENTS.md", "action": "update"}, updated


def detach(repo, *, dry_run: bool) -> dict:
    require_git_root(repo)
    copies = []
    for relative in HOST_COPIES:
        tracked = _tracked(repo, relative)
        if not tracked and not _dirty(repo, relative):
            continue
        if _dirty(repo, relative):
            raise MDFError(f"{relative} 有本地修改或未跟踪文件", code="detach_dirty")
        _guard(tracked or [relative])
        copies.append(relative)
    if not copies:
        return {
            "ok": True, "operation": "detach", "dry_run": dry_run,
            "copies": [], "action": "none",
            "agents": {"path": "AGENTS.md", "action": "skip", "reason": "no_copies"},
        }
    agents, agents_text = _agents_plan(repo)
    payload = {
        "ok": True,
        "operation": "detach",
        "dry_run": dry_run,
        "copies": copies,
        "agents": agents,
    }
    if dry_run:
        payload["action"] = "planned"
        return payload
    if copies:
        removed = run(["git", "rm", "-r", "--", *copies], cwd=repo, check=False)
        if removed.returncode:
            raise MDFError(removed.stderr.strip() or "git rm 失败", code="detach_failed")
        for relative in copies:
            leftover = repo / relative
            if leftover.is_dir() and not leftover.is_symlink():
                shutil.rmtree(leftover)
    if agents_text is not None:
        (repo / "AGENTS.md").write_text(agents_text, encoding="utf-8")
    commit_paths = list(copies)
    if agents.get("action") == "update":
        commit_paths.append("AGENTS.md")
    created = run(
        ["git", "commit", "--only", "-m", MESSAGE, "--", *commit_paths],
        cwd=repo, check=False,
    )
    if created.returncode:
        raise MDFError(
            created.stderr.strip() or created.stdout.strip() or "git commit 失败",
            code="detach_commit_failed",
        )
    payload["action"] = "created"
    payload["commit"] = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    return payload


def command_detach(args) -> None:
    emit(detach(repo_path(args.repo), dry_run=args.dry_run))
