"""verify 的内容指纹凭证：显式输入优先、环境绑定、build 产物完整性与失败吊销（tombstone）。

凭证存于 Git common dir 的 `mdf/attestations/verify/`，同输入指纹只保留最新一条；
命中只复用已存在的通过证据，不启动子进程。
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from mdf_core.execution.modules import load_modules, match, path_ignored
from mdf_core.execution.verification import ENTRIES, SUITES
from mdf_core.foundation.errors import MDFError

PROTOCOL = 1
FIXED_INPUTS = (".mdf/modules.yaml", ".mdf/manifest.yaml", "docs/system/testing/**", "tests/playbooks/**")
LOCKFILES = ("uv.lock", "poetry.lock", "Pipfile.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
             "Cargo.lock", "go.sum", "Gemfile.lock", "composer.lock")
# 默认生成物排除集 G；仅在不属于显式输入 E 时才被排除（E 优先）。
GENERATED = (".mdf/reports/**", ".mdf/logs/**", ".test-reports/**", "changes/**/verification-report.json",
             "changes/**/code-review.md", "changes/**/fact-audit.md", "changes/**/delivery-summary.html",
             "changes/**/CHANGE.md", "CHANGELOG.md")
CACHE_PARTS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "node_modules", ".git"})
PURE_DOCS = ("docs/**", "changes/**", "*.md", "LICENSE*")


def _git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(["git", *args], cwd=repo, input=data, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else b""


def _sha_file(path: Path) -> str:
    if path.is_symlink():
        return hashlib.sha256(os.readlink(path).encode()).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(repo: Path) -> dict[str, str]:
    """tracked + untracked（未忽略）文件的内容摘要；工作区缺失的文件记为 deleted。"""
    files: dict[str, str] = {}
    for row in _git(repo, "ls-files", "-s", "-z").split(b"\0"):
        meta, _, name = row.partition(b"\t")
        if name:
            files[name.decode("utf-8", "replace")] = meta.split()[1].decode()
    dirty = set(_git(repo, "diff-files", "--name-only", "-z").split(b"\0"))
    dirty |= set(_git(repo, "ls-files", "-o", "--exclude-standard", "-z").split(b"\0"))
    for raw in dirty:
        name = raw.decode("utf-8", "replace")
        if not name:
            continue
        path = repo / name
        files[name] = _sha_file(path) if path.is_file() or path.is_symlink() else "deleted"
    return {name: sha for name, sha in files.items() if sha != "deleted"}


def _generated(rel: str) -> bool:
    return bool(CACHE_PARTS & set(rel.split("/"))) or rel.endswith(".pyc") or any(match(rel, p) for p in GENERATED)


def _closure(config, names: list[str]) -> list[str]:
    seen, pending = set(), list(names)
    while pending:
        name = pending.pop()
        if name not in seen:
            seen.add(name)
            pending.extend(config.get(name).depends_on)
    return sorted(seen)


def _named_meta(repo: Path, entry: str) -> dict:
    path = repo / "docs/system/testing" / f"{entry}.md"
    if entry in ENTRIES or not path.is_file():
        return {}
    from mdf_core.foundation.yamlutil import read_frontmatter
    try:
        return read_frontmatter(path)[0]
    except MDFError:
        return {}


def explicit_inputs(repo: Path, config, item: dict, files: dict[str, str]) -> tuple[set[str], bool]:
    """显式执行输入集 E 与 external_state 声明；E 内文件无条件纳入指纹。"""
    entry = item.get("entry") or str(item.get("id", "")).split(":", 1)[0]
    chosen = item.get("module")
    modules = _closure(config, [chosen] if chosen in config.modules else config.names())
    patterns: list[str] = []
    external = False
    for name in modules:
        module = config.get(name)
        if entry in SUITES:
            suite = module.suite(entry)
            patterns += [*suite.tests, *suite.extra_inputs]
            external = external or suite.external_state
    meta = _named_meta(repo, entry)
    patterns += [p for p in meta.get("extra_inputs", []) if isinstance(p, str)]
    external = external or meta.get("external_state") is True
    chosen_modules = [config.get(name) for name in modules]
    result = set()
    for rel in files:
        base = rel.rsplit("/", 1)[-1]
        if (any(match(rel, p) for p in (*FIXED_INPUTS, *patterns)) or base in LOCKFILES
                or (base.startswith("requirements") and base.endswith(".txt"))
                or any(any(match(rel, p) for p in module.sourceset) and not path_ignored(rel, module)
                       for module in chosen_modules)):
            result.add(rel)
    return result, external


def select_inputs(repo: Path, config, item: dict, files: dict[str, str]) -> tuple[dict[str, str], bool]:
    explicit, external = explicit_inputs(repo, config, item, files)
    entry = item.get("entry") or ""
    chosen = item.get("module")
    own = set(_closure(config, [chosen] if chosen in config.modules else config.names()))
    others = [config.get(name) for name in config.names() if name not in own]
    outputs = [p for module in config.modules.values() for p in module.build_artifacts]
    selected = {}
    for rel, sha in files.items():
        if rel not in explicit:
            if _generated(rel) or any(match(rel, p) for p in outputs) or (entry != "lint" and any(match(rel, p) for p in PURE_DOCS)):
                continue
            if config.is_ignored(rel) or any(any(match(rel, p) for p in module.sourceset) for module in others):
                continue
        selected[rel] = sha
    return selected, external


def _tool_digest(command: str) -> str:
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    path = shutil.which(words[0]) if words else None
    if path is None:
        return "shell-builtin-or-missing"
    stat = os.stat(path)
    return f"{os.path.realpath(path)}:{stat.st_size}:{stat.st_mtime_ns}"


def environment(command: str, files: dict[str, str]) -> dict[str, str]:
    locks = sorted((rel, sha) for rel, sha in files.items()
                   if rel.rsplit("/", 1)[-1] in LOCKFILES or rel.rsplit("/", 1)[-1].startswith("requirements"))
    return {"platform": sys.platform, "machine": platform.machine(), "python": platform.python_version(),
            "tool": _tool_digest(command), "lockfile_digest": hashlib.sha256(json.dumps(locks).encode()).hexdigest()}


def fingerprint(repo: Path, item: dict) -> dict[str, Any] | None:
    """无 modules 配置或声明 external_state 时返回 None：不可核验，不复用也不写凭证。"""
    try:
        config = load_modules(repo)
    except MDFError:
        return None
    selected, external = select_inputs(repo, config, item, snapshot(repo))
    if external:
        return None
    inputs = hashlib.sha256("".join(f"{rel}\0{sha}\n" for rel, sha in sorted(selected.items())).encode()).hexdigest()
    env = environment(item["command"], selected)
    ident = {"protocol": PROTOCOL, "id": item["id"], "entry": item.get("entry"), "command": item["command"],
             "budget": item.get("budget"), "inputs": inputs, "env": env}
    key = hashlib.sha256(json.dumps(ident, sort_keys=True).encode()).hexdigest()
    return {"key": key, "inputs": inputs, "env": env, "identity": ident, "config": config}


def _store(repo: Path) -> Path:
    common = _git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip()
    return Path(common) / "mdf" / "attestations" / "verify"


def _read(repo: Path, key: str) -> dict | None:
    path = _store(repo) / f"{key}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _write(repo: Path, key: str, record: dict) -> None:
    directory = _store(repo)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f"{key}.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(directory / f"{key}.json")


def _artifacts(repo: Path, config, item: dict) -> dict[str, str]:
    chosen = item.get("module")
    names = _closure(config, [chosen] if chosen in config.modules else config.names())
    found: dict[str, str] = {}
    for name in names:
        for pattern in config.get(name).build_artifacts:
            for hit in glob.glob(str(repo / pattern), recursive=True):
                path = Path(hit)
                if path.is_file():
                    found[str(path.relative_to(repo))] = _sha_file(path)
    return found


def reusable(repo: Path, item: dict, fp: dict | None, *, downstream_hit: bool = False) -> dict | None:
    """通过凭证且信任校验全部成立才返回；失败吊销、协议/输入/环境不符、证据缺失与 build 产物破损均为 miss。"""
    if fp is None:
        return None
    record = _read(repo, fp["key"])
    if (record is None or record.get("status") != "passed" or record.get("protocol") != PROTOCOL
            or record.get("inputs") != fp["inputs"] or record.get("env") != fp["env"]
            or not record.get("evidence") or not Path(record["evidence"]).is_dir()):
        return None
    if item.get("entry") == "build":
        expected = record.get("artifacts") or {}
        if expected:
            if _artifacts(repo, fp["config"], item) != expected:
                return None
        elif not downstream_hit:
            return None
    return record


def record_result(repo: Path, item: dict, fp: dict | None, detail: dict | None, elapsed: float) -> None:
    """成功写入通过凭证；失败写入 tombstone，覆盖同指纹旧成功凭证。"""
    if fp is None:
        return
    base = {"protocol": PROTOCOL, "key": fp["key"], "id": item["id"], "entry": item.get("entry"),
            "command": item["command"], "inputs": fp["inputs"], "env": fp["env"],
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if detail is None:
        _write(repo, fp["key"], {**base, "status": "failed"})
        return
    log = detail.get("log")
    if not log:
        return
    evidence = str((repo / log).resolve())
    _write(repo, fp["key"], {
        **base, "status": "passed", "exit_code": detail.get("exit_code", 0), "log": log, "evidence": evidence,
        "report": detail.get("report"), "original_duration_s": round(elapsed, 3),
        "artifacts": _artifacts(repo, fp["config"], item) if item.get("entry") == "build" else {},
    })


def reuse_detail(record: dict, check_seconds: float) -> dict[str, Any]:
    result = {"command": record["command"], "exit_code": record.get("exit_code", 0), "log": record["log"],
              "original_duration_s": record["original_duration_s"], "check_duration_s": round(check_seconds, 3),
              "reused_from": {"key": record["key"], "evidence": record["evidence"],
                              "recorded_at": record["recorded_at"]}}
    if record.get("report") is not None:
        result["report"] = record["report"]
    return result


def downstream_hits(repo: Path, items: list[dict]) -> bool:
    """build 无可核验产物时：后续步骤全部命中缓存（无子进程消费产物）才允许跳过。"""
    return bool(items) and all(reusable(repo, item, fingerprint(repo, item)) is not None for item in items)
