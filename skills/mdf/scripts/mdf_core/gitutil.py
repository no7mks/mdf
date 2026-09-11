import re
import subprocess
from pathlib import Path
from typing import Any

from .errors import MDFError
from .paths import relative
from .textutil import slugify, stable_semver


def run(
    args: list[str], *, cwd: Path, check: bool = True
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode:
        raise MDFError(
            completed.stderr.strip() or f"Command failed: {' '.join(args)}",
            code="command_failed",
        )
    return completed


def repo_path(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise MDFError(
            f"Repository path is not a directory: {path}", code="bad_repo"
        )
    return path


def git_root(repo: Path) -> Path | None:
    result = run(["git", "rev-parse", "--show-toplevel"], cwd=repo, check=False)
    if result.returncode:
        return None
    return Path(result.stdout.strip()).resolve()


def require_git_root(repo: Path) -> None:
    root = git_root(repo)
    if root is None:
        raise MDFError(
            "Mars Development Flow requires a Git repository", code="not_git"
        )
    if root != repo:
        raise MDFError(
            f"--repo must be the Git root ({root})",
            code="not_git_root",
        )


def git_is_clean(repo: Path) -> bool:
    result = run(["git", "status", "--porcelain"], cwd=repo)
    return not result.stdout.strip()


def ensure_clean(repo: Path) -> None:
    if not git_is_clean(repo):
        raise MDFError(
            "The Git worktree must be clean before this operation",
            code="dirty_worktree",
        )


def current_branch(repo: Path) -> str:
    require_git_root(repo)
    result = run(["git", "branch", "--show-current"], cwd=repo)
    name = result.stdout.strip()
    if not name:
        raise MDFError("Detached HEAD is unsupported", code="detached_head")
    return name


def branch_details(name: str) -> dict[str, Any]:
    match = re.fullmatch(r"(feature|bugfix)/(.+)", name)
    if match:
        return {
            "name": name,
            "kind": match.group(1),
            "slug": slugify(match.group(2)),
            "version": None,
            "supported": True,
        }
    match = re.fullmatch(r"(release|hotfix)/(.+)", name)
    if match:
        version = match.group(2)
        if stable_semver(version) is None:
            raise MDFError(
                f"{match.group(1)} branch requires a stable SemVer",
                code="bad_release_branch",
            )
        return {
            "name": name,
            "kind": match.group(1),
            "slug": slugify(match.group(2)),
            "version": version,
            "supported": True,
        }
    return {
        "name": name,
        "kind": "unsupported",
        "slug": slugify(name),
        "version": None,
        "supported": False,
    }


def git_directory(repo: Path) -> Path:
    raw = run(["git", "rev-parse", "--git-dir"], cwd=repo).stdout.strip()
    path = Path(raw)
    return (repo / path).resolve() if not path.is_absolute() else path.resolve()


def git_last_commit(repo: Path, path: Path) -> str | None:
    result = run(
        ["git", "log", "-1", "--format=%H", "--", relative(repo, path)],
        cwd=repo,
        check=False,
    )
    value = result.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40,64}", value) else None


def commit_is_after(repo: Path, newer: str, older: str) -> bool:
    if newer == older:
        return False
    result = run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=repo,
        check=False,
    )
    return result.returncode == 0


def git_path_dirty(repo: Path, path: Path) -> bool:
    result = run(
        ["git", "status", "--porcelain", "--", relative(repo, path)],
        cwd=repo,
        check=False,
    )
    return bool(result.stdout.strip())


def git_path_tracked(repo: Path, path: Path) -> bool:
    result = run(
        ["git", "ls-files", "--", relative(repo, path)],
        cwd=repo,
        check=False,
    )
    return bool(result.stdout.strip())


def worktree_map(repo: Path) -> dict[str, Path]:
    raw = run(["git", "worktree", "list", "--porcelain"], cwd=repo).stdout
    worktrees: dict[str, Path] = {}
    for block in raw.strip().split("\n\n"):
        values = dict(
            line.split(" ", 1) for line in block.splitlines() if " " in line
        )
        if "branch" in values:
            name = values["branch"].removeprefix("refs/heads/")
            worktrees[name] = Path(values["worktree"])
    return worktrees


def primary_worktree(repo: Path) -> Path:
    raw = run(["git", "rev-parse", "--git-common-dir"], cwd=repo).stdout.strip()
    path = Path(raw)
    if not path.is_absolute():
        path = (repo / path).resolve()
    else:
        path = path.resolve()
    return path.parent


def sibling_worktree(repo: Path, name: str) -> Path:
    primary = primary_worktree(repo)
    relative = Path(name)
    if relative.is_absolute() or not relative.parts or any(
        part in ("", ".", "..") for part in relative.parts
    ):
        raise MDFError("非法 worktree 名称", code="invalid_worktree")
    return primary.parent / f"{primary.name}-worktrees" / relative


def occupies_delivery(branch: str) -> bool:
    if branch.startswith(("qa/", "dev/")):
        return True
    return bool(branch_details(branch)["supported"])


def add_linked_worktree(
    repo: Path, branch: str, path: Path, start_point: str
) -> None:
    if path.exists():
        raise MDFError("并行分支或 worktree 已存在", code="collision")
    path.parent.mkdir(parents=True, exist_ok=True)
    run(
        ["git", "worktree", "add", "-b", branch, str(path), start_point],
        cwd=repo,
    )
