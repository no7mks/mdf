"""项目内 MDF 本体：`.mdf/cache/mdf-core/<commit>` 只保留一份。只使用标准库。"""

from __future__ import annotations

import ctypes
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - 非 POSIX
    fcntl = None

COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
DEFAULT_SOURCE = "https://github.com/no7mks/mdf.git"
SOURCE_SKILL = "skills/mdf"
CORE_PARENTS = (".mdf", "cache", "mdf-core")
ENTRY_DIR = Path(".agents/skills/mdf")
MDF_IGNORE_HEADER = "# MDF local artifacts"
MDF_IGNORE_LINES = ("/.mdf/logs/", "/.mdf/tmp/", "/.mdf/reports/", "/.mdf/cache/", f"/{ENTRY_DIR.as_posix()}/")


class HomeError(Exception):
    def __init__(self, message: str, code: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details


def core_dir(project: Path) -> Path:
    return project / ".mdf" / "cache" / "mdf-core"


def core_of_launcher(launcher: Path) -> Path:
    raw = Path(os.path.abspath(launcher))
    current = raw.parents[1]
    if (
        raw.parent.name != "scripts"
        or current.parts[-4:-1] != CORE_PARENTS
        or not COMMIT_RE.fullmatch(current.name)
    ):
        raise HomeError("本体不在 .mdf/cache/mdf-core/<commit>", "mdf_core_invalid")
    for path in (raw, *raw.parents[:5]):
        if path.is_symlink():
            raise HomeError(f"{path} 不允许 symbolic link", "mdf_core_invalid")
    if not (current / "SKILL.md").is_file() or not (current / "scripts" / "mdf.py").is_file():
        raise HomeError("本体缺少 SKILL.md 或 scripts/mdf.py", "mdf_core_invalid")
    version = current / "references" / ".version"
    recorded = ""
    if version.is_file() and not version.is_symlink():
        lines = version.read_text(encoding="utf-8").splitlines()
        recorded = lines[0].strip() if lines else ""
    if recorded != current.name:
        raise HomeError("references/.version 与目录名不符", "mdf_core_invalid")
    return current.resolve()


def _run(args: list[str], cwd: Path | None = None, *, text: bool = True):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        args, cwd=cwd, text=text, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False, env=env,
    )


def _git_text(args: list[str], cwd: Path) -> str:
    completed = _run(args, cwd)
    if completed.returncode:
        raise HomeError(
            completed.stderr.strip() or f"命令失败：{' '.join(args)}",
            "command_failed",
        )
    return completed.stdout.strip()


def gitignore_problem(path: Path) -> str | None:
    if path.is_symlink():
        return f".gitignore 不允许 symbolic link: {path}"
    if path.exists() and not path.is_file():
        return f".gitignore 必须是普通文件: {path}"
    return None


def project_gitignore_text(text: str) -> str:
    """补齐 MDF 本地产物的根目录 ignore。"""
    raw_lines = text.splitlines(keepends=True)
    stripped = [line.strip() for line in raw_lines]
    missing = [item for item in MDF_IGNORE_LINES if item not in stripped]
    if not missing:
        return text
    block = "".join(f"{item}\n" for item in missing)
    header_at = next(
        (index for index, line in enumerate(stripped) if line == MDF_IGNORE_HEADER),
        None,
    )
    if header_at is None:
        if not text:
            return f"{MDF_IGNORE_HEADER}\n{block}"
        prefix = text if text.endswith("\n") else text + "\n"
        return f"{prefix}\n{MDF_IGNORE_HEADER}\n{block}"
    end = header_at + 1
    while end < len(stripped) and stripped[end]:
        end += 1
    head = "".join(raw_lines[:end])
    if head and not head.endswith("\n"):
        head += "\n"
    return head + block + "".join(raw_lines[end:])


def read_project_gitignore(repo: Path) -> str:
    path = repo / ".gitignore"
    problem = gitignore_problem(path)
    if problem:
        raise HomeError(problem, "managed_symlink")
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    except UnicodeDecodeError as exc:
        raise HomeError(f".gitignore 不是 UTF-8: {path}", "gitignore_unreadable") from exc


def ensure_project_gitignore(repo: Path) -> list[str]:
    path = repo / ".gitignore"
    old = read_project_gitignore(repo)
    new = project_gitignore_text(old)
    if new == old:
        return []
    present = {line.strip() for line in old.splitlines()}
    path.write_bytes(new.encode("utf-8"))
    return [item for item in MDF_IGNORE_LINES if item not in present]


def _main_worktree(start: Path) -> Path | None:
    completed = _run(["git", "-C", str(start), "worktree", "list", "--porcelain"])
    if completed.returncode:
        return None
    for line in completed.stdout.splitlines():
        if line.startswith("worktree "):
            return Path(line[len("worktree "):]).resolve()
    return None


def _upgrade_repo(explicit: str | None) -> Path:
    if explicit is not None and not explicit.strip():
        raise HomeError("--repo 已设置但为空", "upgrade_repo_invalid")
    if explicit is None:
        start = Path.cwd()
    else:
        start = Path(explicit).expanduser().resolve()
        if not start.is_dir():
            raise HomeError("upgrade --repo 不是目录", "upgrade_repo_invalid")
    main = _main_worktree(start)
    if main is None:
        if explicit is None:
            raise HomeError("当前目录不是 Git 仓库", "upgrade_repo_invalid")
        return start
    if explicit is not None:
        if main != start:
            raise HomeError("upgrade --repo 必须是主 worktree 根目录", "upgrade_repo_invalid")
        return main
    toplevel = Path(_git_text(["git", "rev-parse", "--show-toplevel"], start)).resolve()
    if toplevel != main:
        raise HomeError("必须在主 worktree 中升级", "upgrade_repo_invalid")
    return main


def _reject_cache_symlinks(project: Path) -> None:
    core = core_dir(project)
    paths = (
        project / ".mdf",
        project / ".mdf" / "cache",
        project / ".mdf" / "logs",
        core,
        core / ".lock",
    )
    for path in paths:
        if path.is_symlink():
            raise HomeError(f"{path} 不允许 symbolic link", "managed_symlink")


def write_log(project: Path, operation: str, payload: dict) -> str | None:
    folder = project / ".mdf"
    if not folder.is_dir() or folder.is_symlink():
        return None
    logs = folder / "logs"
    if logs.is_symlink() or (logs.exists() and not logs.is_dir()):
        return None
    logs.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = logs / f"{stamp}-{operation}-{os.getpid()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def installed_revisions(project: Path) -> list[str]:
    core = core_dir(project)
    if not core.is_dir() or core.is_symlink():
        return []
    found = []
    for child in core.iterdir():
        if child.name.startswith(".") or child.is_symlink() or not child.is_dir():
            continue
        if not COMMIT_RE.fullmatch(child.name):
            continue
        version = child / "references" / ".version"
        if not version.is_file() or version.is_symlink():
            continue
        lines = version.read_text(encoding="utf-8").splitlines()
        recorded = lines[0].strip() if lines else ""
        if recorded == child.name:
            found.append(child.name)
    return sorted(found)


def installed_revision(project: Path) -> str | None:
    found = installed_revisions(project)
    return found[0] if len(found) == 1 else None


def self_check(version: Path, log_dir: Path, revision: str) -> None:
    script = version / "scripts" / "mdf.py"
    env = os.environ.copy()
    env["MDF_LOG_DIR"] = str(log_dir)
    completed = subprocess.run(
        [sys.executable, "-B", str(script), "info"],
        capture_output=True, text=True, env=env, check=False,
    )
    if completed.returncode:
        lines = [line for line in completed.stderr.splitlines() if line.strip()]
        detail = lines[-1] if lines else "info 失败"
        raise HomeError(f"自检失败：{detail}", "install_self_check_failed")
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise HomeError("自检失败：info 输出不是 JSON", "install_self_check_failed") from exc
    versions = ("tool_version", "protocol_version", "schema_version")
    matched = data.get("mdf_root") == str(version.resolve()) and data.get("revision") == revision
    if not matched or any(data.get(key) != 3 for key in versions):
        raise HomeError("自检失败：版本目录或契约版本不符", "install_self_check_failed")


def _write_version(version: Path, revision: str) -> None:
    path = version / "references" / ".version"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{revision}\n", encoding="utf-8")


def _chmod_launcher(version: Path) -> None:
    launcher = version / "scripts" / "mdf_launcher.py"
    if launcher.is_file():
        launcher.chmod(launcher.stat().st_mode | 0o755)


def _exchange(left: Path, right: Path) -> None:
    left_b = os.fsencode(left)
    right_b = os.fsencode(right)
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        function = libc.renameatx_np
        at_fdcwd = -2
    elif sys.platform == "linux":
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        function = libc.renameat2
        at_fdcwd = -100
    else:
        raise HomeError(f"当前平台不能原子交换目录：{sys.platform}", "core_swap_unsupported")
    function.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
    ]
    function.restype = ctypes.c_int
    if function(at_fdcwd, left_b, at_fdcwd, right_b, 2) != 0:
        err = ctypes.get_errno()
        raise HomeError(f"原子交换目录失败：{os.strerror(err)}", "core_swap_unsupported")


def _drop(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _clear_staging(core: Path) -> None:
    if not core.is_dir():
        return
    for child in list(core.iterdir()):
        if child.name.startswith(".staging-"):
            _drop(child)


@contextmanager
def core_lock(core: Path):
    if fcntl is None:
        raise HomeError("本体锁需要 POSIX fcntl", "mdf_core_locked")
    lock = core / ".lock"
    if lock.is_symlink():
        raise HomeError(f"{lock} 不允许 symbolic link", "managed_symlink")
    core.mkdir(parents=True, exist_ok=True)
    handle = lock.open("a+b")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _prepare_core(project: Path) -> Path:
    core = core_dir(project)
    for path in (
        project / ".mdf", project / ".mdf" / "cache", project / ".mdf" / "logs",
        core, core / ".lock",
    ):
        if path.is_symlink():
            raise HomeError(f"{path} 不允许 symbolic link", "managed_symlink")
    core.mkdir(parents=True, exist_ok=True)
    return core


def _replace_dir(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() and not dest.is_symlink():
        os.rename(src, dest)
        return
    if dest.is_symlink() or not dest.is_dir():
        dest.unlink()
        os.rename(src, dest)
        return
    _exchange(src, dest)
    shutil.rmtree(src)


def _entry_destination(project: Path, *, from_entry: bool) -> Path | None:
    cursor = project
    for part in ENTRY_DIR.parts:
        cursor = cursor / part
        if cursor.is_symlink() or (cursor.exists() and not cursor.is_dir()):
            raise HomeError(f"{cursor} 必须是实际目录", "managed_symlink")
    tracked = _run(["git", "ls-files", "-z", "--", ENTRY_DIR.as_posix()], project, text=False)
    if tracked.returncode == 0 and tracked.stdout:
        if from_entry and os.fsencode(ENTRY_DIR / "mdf_entry.py") in tracked.stdout.split(b"\0"):
            return None
        raise HomeError(f"{ENTRY_DIR} 含已跟踪文件，请先执行 detach", "entry_tracked")
    return cursor


def _render_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise HomeError(f"入口模板缺少唯一的 {label}", "install_missing_host_skill")
    return text.replace(old, new, 1)


def _host_files(tree: Path, revision: str, source: str) -> dict[str, bytes]:
    skill = tree / "assets" / "host" / "SKILL.md"
    spec = tree / "agents" / "openai.yaml"
    entry = tree / "assets" / "host" / "mdf_entry.py"
    if not skill.is_file() or not spec.is_file() or not entry.is_file():
        raise HomeError("版本缺少引导指针", "install_missing_host_skill")
    rendered_entry = _render_once(entry.read_text(encoding="utf-8"), 'REVISION = ""', "REVISION = " + json.dumps(revision), "REVISION")
    rendered_entry = _render_once(rendered_entry, 'SOURCE = ""', "SOURCE = " + json.dumps(source), "SOURCE")
    return {
        "SKILL.md": skill.read_bytes(),
        "agents/openai.yaml": spec.read_bytes(),
        "mdf_entry.py": rendered_entry.encode("utf-8"),
    }


def _host_matches(dest: Path, files: dict[str, bytes]) -> bool:
    if not dest.is_dir() or dest.is_symlink():
        return False
    present = {
        path.relative_to(dest).as_posix()
        for path in dest.rglob("*") if path.is_file() and not path.is_symlink()
    }
    if present != set(files):
        return False
    return all((dest / name).read_bytes() == data for name, data in files.items())


def install_entry(dest: Path, tree: Path, revision: str, source: str) -> None:
    files = _host_files(tree, revision, source)
    if _host_matches(dest, files):
        return
    stage: Path | None = None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".host-stage-", dir=dest.parent))
        for name, data in files.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        _replace_dir(stage, dest)
    except OSError as exc:
        raise HomeError(f"仓库引导更新失败：{exc}", "host_update_failed") from exc
    finally:
        if stage is not None:
            _drop(stage)


def _keep_only(core: Path, revision: str) -> None:
    for child in list(core.iterdir()):
        if child.name in {revision, ".lock"}:
            continue
        _drop(child)


def _version_ready(dest: Path, revision: str, log_dir: Path) -> bool:
    if not dest.is_dir() or dest.is_symlink():
        return False
    try:
        self_check(dest, log_dir, revision)
        core_of_launcher(dest / "scripts" / "mdf_launcher.py")
    except (HomeError, OSError, IndexError):
        return False
    return True


def install_payload(project: Path, revision: str, payload: Path, source: str, *, from_entry: bool = False) -> dict:
    if not COMMIT_RE.fullmatch(revision):
        raise HomeError("revision 必须是完整 commit hash", "invalid_revision")
    project = project.resolve()
    source = _entry_source(source)
    required = (
        payload / "scripts" / "mdf.py",
        payload / "scripts" / "mdf_launcher.py",
        payload / "scripts" / "mdf_home.py",
        payload / "SKILL.md",
        payload / "agents" / "openai.yaml",
        payload / "assets" / "host" / "SKILL.md",
        payload / "assets" / "host" / "mdf_entry.py",
    )
    if not payload.is_dir() or any(not path.is_file() for path in required):
        raise HomeError("payload 缺少本体文件", "install_missing_payload")
    read_project_gitignore(project)
    _reject_cache_symlinks(project)
    entry = _entry_destination(project, from_entry=from_entry)
    core = _prepare_core(project)
    dest = core / revision
    log_dir = project / ".mdf" / "logs"
    with core_lock(core):
        _clear_staging(core)
        if dest.is_symlink():
            raise HomeError(f"{dest} 不允许 symbolic link", "managed_symlink")
        if not _version_ready(dest, revision, log_dir):
            staging = core / f".staging-{os.getpid()}"
            placed = False
            try:
                if dest.exists() or dest.is_symlink():
                    parked = core / f".staging-old-{os.getpid()}"
                    os.rename(dest, parked)
                    _drop(parked)
                shutil.copytree(payload, staging)
                _write_version(staging, revision)
                _chmod_launcher(staging)
                self_check(staging, log_dir, revision)
                os.rename(staging, dest)
                placed = True
                core_of_launcher(dest / "scripts" / "mdf_launcher.py")
            except HomeError:
                _drop(staging)
                if placed:
                    _drop(dest)
                raise
            except Exception as exc:
                _drop(staging)
                if placed:
                    _drop(dest)
                raise HomeError(f"自检失败：{exc}", "install_self_check_failed") from exc
        if entry is not None:
            ensure_project_gitignore(project)
            install_entry(entry, dest, revision, source)
        try:
            _keep_only(core, revision)
        except OSError as exc:
            raise HomeError(
                f"旧本体未删除：{exc}",
                "core_cleanup_failed",
                {"path": str(core)},
            ) from exc
    body = {
        "ok": True,
        "operation": "install-payload",
        "repo": str(project),
        "revision": revision,
        "root": str(dest.resolve()),
    }
    body["log"] = write_log(project, "install", body)
    return body


def _extract_tar(data: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        kwargs: dict[str, object] = {}
        if sys.version_info >= (3, 12):
            kwargs["filter"] = "data"
        tar.extractall(dest, **kwargs)


def _clone(source: str, dest: Path) -> None:
    completed = _run(["git", "clone", "--depth", "1", "--", source, str(dest)])
    if completed.returncode:
        raise HomeError(
            completed.stderr.strip() or f"git clone 失败：{source}",
            "upgrade_clone_failed",
        )


def _has_commit(clone: Path, commit: str) -> bool:
    return _run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], clone).returncode == 0


def _ensure_commit(clone: Path, commit: str) -> bool:
    if not _has_commit(clone, commit):
        _run(["git", "fetch", "--unshallow"], clone)
    return _has_commit(clone, commit)


def _skill_path(raw: str) -> str:
    prefix = f"{SOURCE_SKILL}/"
    if raw.startswith(prefix):
        return raw[len(prefix):]
    return "." if raw == SOURCE_SKILL else raw


def _changed_files(clone: Path, old: str, new: str) -> list[dict[str, str]]:
    text = _git_text(["git", "diff", "--name-status", old, new, "--", SOURCE_SKILL], clone)
    files: list[dict[str, str]] = []
    for line in text.splitlines():
        status, _, rest = line.partition("\t")
        path = rest.split("\t")[-1] if rest else ""
        if status and path:
            files.append({"status": status, "path": _skill_path(path)})
    return files


def skill_history(clone: Path, old: str | None, new: str) -> dict:
    result: dict = {"from": old, "to": new, "status": "ok", "commits": [], "files": []}
    if not old:
        result["status"] = "no_current_version"
        return result
    if old == new:
        result["status"] = "same"
        return result
    if not COMMIT_RE.fullmatch(old) or not _ensure_commit(clone, old):
        result["status"] = "unknown_base"
        return result
    log = _git_text(
        ["git", "log", "--format=%H%x09%s", f"{old}..{new}", "--", SOURCE_SKILL], clone,
    )
    commits = []
    for line in log.splitlines():
        commit, _, subject = line.partition("\t")
        if commit:
            commits.append({"commit": commit, "subject": subject})
    result["commits"] = commits
    result["files"] = _changed_files(clone, old, new)
    return result


def _fetch(source: str) -> tuple[str, Path, tempfile.TemporaryDirectory[str]]:
    temp = tempfile.TemporaryDirectory()
    clone = Path(temp.name) / "source"
    try:
        _clone(source, clone)
        commit = _git_text(["git", "rev-parse", "HEAD"], clone)
        if not (clone / SOURCE_SKILL).is_dir():
            raise HomeError(f"上游缺少 {SOURCE_SKILL}", "upgrade_missing_skill")
        if not COMMIT_RE.fullmatch(commit):
            raise HomeError("上游 HEAD 不是完整 commit hash", "invalid_revision")
    except Exception:
        temp.cleanup()
        raise
    return commit, clone, temp


def _run_payload_install(
    launcher: Path, project: Path, revision: str, payload: Path, source: str,
) -> dict:
    completed = subprocess.run(
        [
            sys.executable, "-B", str(launcher), "install-payload",
            "--revision", revision, "--payload", str(payload),
            "--repo", str(project), "--source", source,
        ],
        capture_output=True, text=True, check=False,
    )
    if not completed.returncode:
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise HomeError("install-payload 输出不是 JSON", "install_self_check_failed") from exc
        return parsed if isinstance(parsed, dict) else {}
    lines = [line for line in completed.stderr.splitlines() if line.strip()]
    detail = lines[-1] if lines else "install-payload 失败"
    code = "install_self_check_failed"
    try:
        parsed = json.loads(detail)
        if isinstance(parsed, dict) and parsed.get("error"):
            code = str(parsed["error"])
            detail = str(parsed.get("message") or detail)
    except json.JSONDecodeError:
        pass
    raise HomeError(detail, code)


def _entry_source(source: str) -> str:
    if not source.strip():
        raise HomeError("--source 已设置但为空", "upgrade_repo_invalid")
    candidate = Path(source).expanduser()
    if candidate.exists():
        return str(candidate.resolve())
    return source


def upgrade(
    project_arg: str | None, source: str, *, dry_run: bool, expected: str | None,
) -> dict:
    source = _entry_source(source)
    if not dry_run and not COMMIT_RE.fullmatch(expected or ""):
        raise HomeError("替换需要预览确认的完整 commit", "missing_expected_commit")
    project = _upgrade_repo(project_arg)
    _reject_cache_symlinks(project)
    read_project_gitignore(project)
    commit, clone, temp = _fetch(source)
    try:
        if not dry_run and commit != expected:
            raise HomeError(
                "上游已变化，须重新预览并确认",
                "upgrade_source_changed",
                {"expected": expected, "actual": commit},
            )
        old = installed_revision(project)
        installed = None if old is None else core_dir(project) / old
        payload = {
            "ok": True,
            "operation": "upgrade",
            "dry_run": dry_run,
            "source": source,
            "new_commit": commit,
            "revision": old,
            "history": skill_history(clone, old, commit),
            "repo": str(project),
            "root": (
                str(installed.resolve())
                if installed is not None and installed.is_dir() and not installed.is_symlink()
                else None
            ),
        }
        if dry_run:
            payload["log"] = None
            return payload
        archive = _run(
            ["git", "archive", "--format=tar", f"{commit}:{SOURCE_SKILL}"], clone, text=False,
        )
        if archive.returncode:
            err = archive.stderr.decode().strip() if archive.stderr else ""
            raise HomeError(err or "git archive 失败", "upgrade_archive_failed")
        with tempfile.TemporaryDirectory() as extracted_root:
            extracted = Path(extracted_root) / "skill"
            _extract_tar(archive.stdout, extracted)
            launcher = extracted / "scripts" / "mdf_launcher.py"
            if not launcher.is_file():
                raise HomeError("归档缺少 scripts/mdf_launcher.py", "upgrade_missing_skill")
            installed_payload = _run_payload_install(launcher, project, commit, extracted, source)
        payload["revision"] = commit
        payload["root"] = str(installed_payload.get("root") or (core_dir(project) / commit).resolve())
        payload["log"] = installed_payload.get("log")
        return payload
    finally:
        temp.cleanup()
