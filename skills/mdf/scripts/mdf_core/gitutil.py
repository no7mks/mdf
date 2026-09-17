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


# 同一进程内目录所属的 Git 根不会改变；只缓存已确认的根，避免重复 rev-parse。
_GIT_ROOTS: dict[Path, Path] = {}


def git_root(repo: Path) -> Path | None:
    cached = _GIT_ROOTS.get(repo)
    if cached is not None:
        return cached
    result = run(["git", "rev-parse", "--show-toplevel"], cwd=repo, check=False)
    if result.returncode:
        return None
    root = Path(result.stdout.strip()).resolve()
    _GIT_ROOTS[repo] = root
    return root


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


_IN_PROGRESS_HEADS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")


def git_in_progress_head(repo: Path) -> str | None:
    git_dir = git_directory(repo)
    for name in _IN_PROGRESS_HEADS:
        if (git_dir / name).is_file():
            return name
    return None


def git_is_clean(repo: Path) -> bool:
    if git_in_progress_head(repo) is not None:
        return False
    result = run(["git", "status", "--porcelain"], cwd=repo)
    return not result.stdout.strip()


def ensure_clean(repo: Path) -> None:
    if git_is_clean(repo):
        return
    head = git_in_progress_head(repo)
    suffix = f" ({head} exists)" if head else ""
    raise MDFError(
        f"The Git worktree must be clean before this operation{suffix}",
        code="dirty_worktree",
    )


def current_branch(repo: Path) -> str:
    require_git_root(repo)
    result = run(["git", "branch", "--show-current"], cwd=repo)
    name = result.stdout.strip()
    if not name:
        raise MDFError("Detached HEAD is unsupported", code="detached_head")
    return name


def require_planning(repo: Path) -> None:
    if current_branch(repo) != "planning":
        raise MDFError(
            "规划写入只能在 planning 分支上分配或写入",
            code="proposal_not_on_planning",
        )


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


def unreleased_slug(details: dict[str, Any]) -> str:
    kind = details.get("kind")
    if kind in {"release", "hotfix"}:
        version = details.get("version")
        if not isinstance(version, str) or stable_semver(version) is None:
            raise MDFError(
                "release/hotfix 审查目录必须使用稳定 SemVer",
                code="bad_release_branch",
            )
        return version
    if kind in {"feature", "bugfix"}:
        slug = details.get("slug")
        if not isinstance(slug, str) or not slug:
            raise MDFError("交付 slug 缺失", code="unsupported_branch")
        return slug
    raise MDFError("需要 Gitflow 交付分支", code="unsupported_branch")


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


def _with_parents(names: list[str]) -> set[str]:
    found: set[str] = set()
    for name in names:
        if not name:
            continue
        found.add(name)
        parts = name.split("/")
        for depth in range(1, len(parts)):
            found.add("/".join(parts[:depth]))
        found.add(".")
    return found


def _status_paths(raw: str) -> list[str]:
    entries = raw.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            paths.append(entries[index])
            index += 1
    return paths


class GitPathIndex:
    """一次性读取跟踪与脏状态，供同一校验内的重复路径查询复用。"""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self._tracked: set[str] | None = None
        self._dirty: set[str] | None = None
        self._commits: dict[str, str | None] = {}

    def tracked(self, path: Path) -> bool:
        if self._tracked is None:
            raw = run(["git", "ls-files", "-z"], cwd=self.repo, check=False)
            self._tracked = _with_parents(raw.stdout.split("\0"))
        return relative(self.repo, path) in self._tracked

    def dirty(self, path: Path) -> bool:
        if self._dirty is None:
            raw = run(
                ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
                cwd=self.repo,
                check=False,
            )
            self._dirty = _with_parents(_status_paths(raw.stdout))
        return relative(self.repo, path) in self._dirty

    def last_commit(self, path: Path) -> str | None:
        rel = relative(self.repo, path)
        if rel not in self._commits:
            self._commits[rel] = git_last_commit(self.repo, path)
        return self._commits[rel]


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
