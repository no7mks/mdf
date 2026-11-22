"""仓外安装根：发现版本、原子切换、安装、升级与回滚。只使用标准库。"""

from __future__ import annotations

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
# Codex 与 Cursor 读取 ~/.agents/skills。再写入二者的专属目录会显示两个同名 Skill。
HOST_SKILLS = (
    ".agents/skills",
    ".claude/skills",
    ".kiro/skills",
    ".openclaw/skills",
)
HOST_SCRIPTS = ("mdf_launcher.py", "mdf_home.py")


class HomeError(Exception):
    def __init__(self, message: str, code: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details


def select_root(explicit: str | None) -> tuple[Path, str]:
    """返回安装根，以及 current 无效时使用的错误码。"""
    if explicit is not None:
        if not explicit.strip():
            raise HomeError("--home 已设置但为空", "mdf_home_invalid")
        return Path(explicit).expanduser().resolve(), "mdf_home_invalid"
    raw = os.environ.get("MDF_HOME")
    if raw is None:
        return (Path.home() / ".local" / "share" / "mdf").resolve(), "mdf_install_invalid"
    if not raw.strip():
        raise HomeError("MDF_HOME 已设置但为空", "mdf_home_invalid")
    return Path(raw).expanduser().resolve(), "mdf_home_invalid"


def invalid_message(root: Path, reason: str, code: str) -> str:
    if code == "mdf_home_invalid":
        return f"MDF_HOME={root} 无效：{reason}"
    return f"默认安装 {root} 无效：{reason}；运行 mdf-deploy.sh install"


def resolve_version(root: Path, code: str) -> tuple[Path, str]:
    link = root / "current"
    if not link.is_symlink():
        reason = f"{link} 不存在" if not link.exists() else f"{link} 不是符号链接"
        raise HomeError(invalid_message(root, reason, code), code)
    target = os.readlink(link)
    parts = Path(target).parts
    if len(parts) != 2 or parts[0] != "versions" or not COMMIT_RE.fullmatch(parts[1]):
        reason = f"{link} 未指向 versions/<完整 commit>"
        raise HomeError(invalid_message(root, reason, code), code)
    revision = parts[1]
    version = (root / "versions" / revision).resolve()
    script = version / "scripts" / "mdf.py"
    if not script.is_file():
        reason = f"versions/{revision} 缺少 scripts/mdf.py"
        raise HomeError(invalid_message(root, reason, code), code)
    version_file = version / "references" / ".version"
    recorded = ""
    if version_file.is_file():
        lines = version_file.read_text(encoding="utf-8").splitlines()
        recorded = lines[0].strip() if lines else ""
    if recorded != revision:
        reason = "references/.version 与目录名不符"
        raise HomeError(invalid_message(root, reason, code), code)
    return version, revision


def current_revision(root: Path) -> str | None:
    try:
        _, revision = resolve_version(root, "mdf_install_invalid")
    except HomeError:
        return None
    return revision


@contextmanager
def home_lock(root: Path):
    if fcntl is None:
        raise HomeError("安装锁需要 POSIX fcntl", "mdf_home_locked")
    root.mkdir(parents=True, exist_ok=True)
    handle = (root / ".lock").open("a+b")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _switch(root: Path, revision: str) -> str | None:
    current = root / "current"
    previous = os.readlink(current) if current.is_symlink() else None
    if current.exists() and not current.is_symlink():
        raise HomeError(f"{current} 不是符号链接", "mdf_install_invalid")
    temp = root / f"current.{os.getpid()}"
    try:
        if temp.is_symlink() or temp.exists():
            temp.unlink()
        temp.symlink_to(Path("versions") / revision)
        os.replace(temp, current)
    finally:
        if temp.is_symlink() or temp.exists():
            temp.unlink()
    return previous


def _restore_link(root: Path, previous: str | None) -> None:
    current = root / "current"
    if previous is None:
        if current.is_symlink() or current.exists():
            current.unlink()
        return
    temp = root / f"current.{os.getpid()}"
    try:
        if temp.is_symlink() or temp.exists():
            temp.unlink()
        temp.symlink_to(previous)
        os.replace(temp, current)
    finally:
        if temp.is_symlink() or temp.exists():
            temp.unlink()


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


def write_log(root: Path, operation: str, payload: dict) -> str:
    folder = root / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = folder / f"{stamp}-{operation}-{os.getpid()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


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


def _replace_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.parent / f".{dest.name}.{os.getpid()}"
    try:
        shutil.copyfile(src, temporary)
        if src.stat().st_mode & 0o111:
            temporary.chmod(temporary.stat().st_mode | 0o755)
        os.replace(temporary, dest)
    finally:
        if temporary.exists():
            temporary.unlink()


def _host_paths() -> list[Path]:
    return [Path.home() / relative / "mdf" for relative in HOST_SKILLS]


def _backup_hosts(backup: Path) -> None:
    records: list[dict[str, str]] = []
    for index, dest in enumerate(_host_paths()):
        record = {"index": str(index), "dest": str(dest)}
        slot = backup / str(index)
        if dest.is_symlink():
            record["kind"] = "symlink"
            record["target"] = os.readlink(dest)
        elif dest.is_dir():
            record["kind"] = "dir"
            shutil.copytree(dest, slot, symlinks=True)
        elif dest.exists():
            record["kind"] = "file"
            shutil.copy2(dest, slot)
        else:
            record["kind"] = "absent"
        records.append(record)
    (backup / "manifest.json").write_text(
        json.dumps(records), encoding="utf-8",
    )


def _restore_hosts(backup: Path) -> None:
    records = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    for record in records:
        dest = Path(record["dest"])
        if dest.is_symlink() or dest.exists():
            if dest.is_dir() and not dest.is_symlink():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        kind = record["kind"]
        if kind == "absent":
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        slot = backup / record["index"]
        if kind == "symlink":
            dest.symlink_to(record["target"])
        elif kind == "dir":
            shutil.copytree(slot, dest, symlinks=True)
        else:
            shutil.copy2(slot, dest)


def install_hosts(version: Path) -> list[str]:
    skill = version / "assets" / "host" / "SKILL.md"
    spec = version / "agents" / "openai.yaml"
    scripts = [version / "scripts" / name for name in HOST_SCRIPTS]
    if not skill.is_file():
        raise HomeError("版本缺少 assets/host/SKILL.md", "install_missing_host_skill")
    for path in scripts:
        if not path.is_file():
            raise HomeError(f"版本缺少 scripts/{path.name}", "install_missing_host_skill")
    written: list[str] = []
    for relative in HOST_SKILLS:
        dest = Path.home() / relative / "mdf"
        if dest.is_symlink():
            dest.unlink()
        dest.mkdir(parents=True, exist_ok=True)
        _replace_file(skill, dest / "SKILL.md")
        if spec.is_file():
            _replace_file(spec, dest / "agents" / "openai.yaml")
        for path in scripts:
            _replace_file(path, dest / "scripts" / path.name)
        written.append(str(dest))
    return written


def ensure_bin(root: Path) -> str | None:
    directory = Path.home() / ".local" / "bin"
    directory.mkdir(parents=True, exist_ok=True)
    link = directory / "mdf"
    if link.exists() or link.is_symlink():
        return None
    link.symlink_to(root / "current" / "scripts" / "mdf_launcher.py")
    return str(link)


def _current_restored(root: Path, previous: str | None, version_dir: Path) -> bool:
    """current 已回到切换前的目标，且该目标不是即将删除的新版本目录。"""
    current = root / "current"
    try:
        if previous is None:
            return not current.is_symlink() and not current.exists()
        if not current.is_symlink() or os.readlink(current) != previous:
            return False
        target = root / previous
        if not target.exists():
            return False
        return target.resolve() != version_dir.resolve()
    except OSError:
        return False


def _discard_tree(path: Path) -> None:
    """先把目录改名再删除，避免删到一半时原路径仍被占用。"""
    if not path.exists() and not path.is_symlink():
        return
    holding = Path(tempfile.mkdtemp(prefix=f".discard-{path.name}-", dir=path.parent))
    os.replace(path, holding / "tree")
    shutil.rmtree(holding)


def _activate(root: Path, revision: str, *, created: bool) -> str | None:
    version_dir = root / "versions" / revision
    version = version_dir.resolve()
    try:
        self_check(version, root / "logs", revision)
    except Exception:
        if created:
            shutil.rmtree(version_dir, ignore_errors=True)
        raise
    backup: Path | None = None
    switched = False
    previous: str | None = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        prefix = f".host-backup-{stamp}-{os.getpid()}-"
        backup = Path(tempfile.mkdtemp(prefix=prefix, dir=root))
        _backup_hosts(backup)
        previous = _switch(root, revision)
        switched = True
        install_hosts(version)
        ensure_bin(root)
    except (Exception, KeyboardInterrupt) as exc:
        failures: list[str] = []
        current_restored = not switched
        if switched:
            try:
                _restore_hosts(backup)
            except Exception as restore_exc:
                failures.append(f"宿主引导壳：{restore_exc}")
            try:
                _restore_link(root, previous)
            except Exception as restore_exc:
                failures.append(f"current：{restore_exc}")
            else:
                current_restored = _current_restored(root, previous, version_dir)
                if not current_restored:
                    failures.append("current：未恢复到先前有效目标")
        if created and current_restored:
            try:
                _discard_tree(version_dir)
            except OSError as discard_exc:
                failures.append(f"新版本目录：{discard_exc}")
        if failures:
            joined = "；".join(failures)
            details: dict[str, object] = {
                "backup": str(backup),
                "cause": str(exc),
                "rollback_failures": failures,
            }
            kept = f"备份保留在 {backup}"
            if version_dir.exists():
                details["version"] = str(version_dir)
                kept = f"新版本目录保留在 {version_dir}；{kept}"
            raise HomeError(
                f"宿主引导壳更新失败且回滚未完成：{exc}；{joined}；{kept}",
                "host_rollback_incomplete",
                details,
            ) from exc
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
        if isinstance(exc, KeyboardInterrupt):
            raise
        if isinstance(exc, HomeError):
            raise
        raise HomeError(f"宿主引导壳更新失败：{exc}", "host_update_failed") from exc
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)
    return previous


def install_payload(root: Path, revision: str, payload: Path) -> dict:
    if not COMMIT_RE.fullmatch(revision):
        raise HomeError("revision 必须是完整 commit hash", "invalid_revision")
    if not payload.is_dir() or not (payload / "scripts" / "mdf.py").is_file():
        raise HomeError("payload 缺少 scripts/mdf.py", "install_missing_payload")
    if not (payload / "assets" / "host" / "SKILL.md").is_file():
        raise HomeError("payload 缺少 assets/host/SKILL.md", "install_missing_host_skill")
    for name in HOST_SCRIPTS:
        if not (payload / "scripts" / name).is_file():
            raise HomeError(f"payload 缺少 scripts/{name}", "install_missing_host_skill")
    with home_lock(root):
        dest = root / "versions" / revision
        created = not dest.exists()
        if created:
            staging = root / "versions" / f".staging-{revision}-{os.getpid()}"
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(payload, staging)
            _write_version(staging, revision)
            _chmod_launcher(staging)
            staging.rename(dest)
        elif not (dest / "scripts" / "mdf.py").is_file():
            raise HomeError(f"versions/{revision} 已存在且不完整", "revision_exists")
        try:
            previous = _activate(root, revision, created=created)
        except HomeError:
            raise
        except Exception as exc:
            raise HomeError(f"自检失败：{exc}", "install_self_check_failed") from exc
        payload_out = {
            "ok": True,
            "operation": "install-payload",
            "home": str(root),
            "revision": revision,
            "root": str(dest.resolve()),
            "previous": previous,
            "created": created,
        }
        payload_out["log"] = write_log(root, "install-payload", payload_out)
        return payload_out


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


def upgrade(root: Path, source: str, *, dry_run: bool, expected: str | None) -> dict:
    if not dry_run and not COMMIT_RE.fullmatch(expected or ""):
        raise HomeError("替换需要预览确认的完整 commit", "missing_expected_commit")
    commit, clone, temp = _fetch(source)
    try:
        if not dry_run and commit != expected:
            raise HomeError(
                "上游已变化，须重新预览并确认",
                "upgrade_source_changed",
                {"expected": expected, "actual": commit},
            )
        old = current_revision(root)
        history = skill_history(clone, old, commit)
        payload = {
            "ok": True,
            "operation": "upgrade",
            "dry_run": dry_run,
            "source": source,
            "new_commit": commit,
            "revision": old,
            "history": history,
            "home": str(root),
        }
        if dry_run:
            payload["log"] = write_log(root, "upgrade", payload)
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
            completed = subprocess.run(
                [
                    sys.executable, "-B", str(launcher), "install-payload",
                    "--revision", commit, "--payload", str(extracted), "--home", str(root),
                ],
                capture_output=True, text=True, check=False,
            )
        if completed.returncode:
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
        payload["revision"] = commit
        payload["rolled_back"] = False
        payload["log"] = write_log(root, "upgrade", payload)
        return payload
    finally:
        temp.cleanup()


def list_versions(root: Path) -> list[str]:
    folder = root / "versions"
    if not folder.is_dir():
        return []
    return sorted(
        path.name for path in folder.iterdir()
        if path.is_dir() and not path.is_symlink() and COMMIT_RE.fullmatch(path.name)
    )


def restore(root: Path, revision: str | None) -> dict:
    with home_lock(root):
        installed = list_versions(root)
        current = current_revision(root)
        if revision is None:
            payload = {
                "ok": True, "operation": "restore", "current": current,
                "versions": installed, "home": str(root), "changed": False,
            }
            payload["log"] = write_log(root, "restore", payload)
            return payload
        if not COMMIT_RE.fullmatch(revision) or revision not in installed:
            raise HomeError(f"未安装修订 {revision}", "restore_missing_revision")
        if current == revision:
            payload = {
                "ok": True, "operation": "restore", "current": current,
                "revision": revision, "changed": False, "home": str(root),
            }
            payload["log"] = write_log(root, "restore", payload)
            return payload
        previous = _activate(root, revision, created=False)
        payload = {
            "ok": True, "operation": "restore", "previous": previous,
            "revision": revision, "changed": True, "home": str(root),
            "root": str((root / "versions" / revision).resolve()),
        }
        payload["log"] = write_log(root, "restore", payload)
        return payload
