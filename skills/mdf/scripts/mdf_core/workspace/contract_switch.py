"""把业务仓 manifest 的 schema_version 切到本机契约。不跑其他门禁。"""

from __future__ import annotations

import re
from pathlib import Path

from mdf_core.foundation.constants import SCHEMA_VERSION
from mdf_core.foundation.errors import MDFError, emit
from mdf_core.foundation.paths import load_manifest, manifest_path
from mdf_core.workspace.gitutil import current_branch, ensure_clean, repo_path, require_git_root, run
from mdf_core.workspace.merge_policy import configured, manifest_at, paths
from mdf_core.workspace.workflow_policy import trunk_branch

CONTRACT_BRANCH = "codex/contract-switch"
MANIFEST = ".mdf/manifest.yaml"
_SCHEMA_LINE = re.compile(r"^schema_version: (\d+)$", re.M)


def schema_in_text(text: str) -> int | None:
    found = [int(match.group(1)) for match in _SCHEMA_LINE.finditer(text)]
    if len(found) != 1:
        return None
    return found[0]


def replace_schema_line(text: str, new: int) -> str:
    matches = list(_SCHEMA_LINE.finditer(text))
    if len(matches) != 1:
        raise MDFError(
            "manifest 必须恰好有一行 schema_version: <整数>",
            code="manifest.schema",
        )
    match = matches[0]
    return text[: match.start()] + f"schema_version: {new}" + text[match.end() :]


def drift_hint(repo: Path) -> str | None:
    """工作区与 origin trunk 中较大的 schema_version 高于本机时，返回一行提示。"""
    shown = run(["git", "rev-parse", "--show-toplevel"], cwd=repo, check=False)
    if shown.returncode == 0 and shown.stdout.strip():
        repo = Path(shown.stdout.strip())
    best: int | None = None
    label = ""
    path = manifest_path(repo)
    if path.is_file() and not path.is_symlink():
        local = schema_in_text(path.read_text(encoding="utf-8"))
        if local is not None:
            best, label = local, ".mdf/manifest.yaml"
    try:
        trunk = trunk_branch(repo)
        ref = f"refs/remotes/origin/{trunk}:{MANIFEST}"
        shown = run(["git", "show", ref], cwd=repo, check=False)
        if shown.returncode == 0:
            remote = schema_in_text(shown.stdout)
            if remote is not None and (best is None or remote >= best):
                best, label = remote, f"origin/{trunk}"
    except (MDFError, OSError):
        pass
    if best is None or best <= SCHEMA_VERSION:
        return None
    return (
        f"MDF 提示：本机 MDF 契约 {SCHEMA_VERSION} 低于 {label} 声明的 {best}；"
        "更新命令：mdf upgrade"
    )


def _only_schema_line(old: str, new: str, old_version: int, new_version: int) -> bool:
    if schema_in_text(old) != old_version or schema_in_text(new) != new_version:
        return False
    return replace_schema_line(old, new_version) == new


def _file_mode(repo: Path, ref: str, path: str) -> str | None:
    entry = run(["git", "ls-tree", ref, "--", path], cwd=repo, check=False).stdout.split()
    return entry[0] if entry else None


def valid_contract_source(repo: Path, base: str, head: str, target: str) -> bool:
    """PR source 只有一个 parent，且只把 schema_version 升到本机契约。"""
    parents = run(["git", "show", "-s", "--format=%P", head], cwd=repo).stdout.split()
    if parents != [base]:
        return False
    if trunk_branch(repo, base) != target or configured(repo, base).get("mode") != "pr":
        return False
    if set(paths(repo, base, head)) != {MANIFEST}:
        return False
    old_mode = _file_mode(repo, base, MANIFEST)
    if old_mode not in {"100644", "100755"} or old_mode != _file_mode(repo, head, MANIFEST):
        return False
    old = manifest_at(repo, base).get("schema_version")
    new = manifest_at(repo, head).get("schema_version")
    if not isinstance(old, int) or isinstance(old, bool) or old >= SCHEMA_VERSION:
        return False
    if new != SCHEMA_VERSION:
        return False
    old_text = run(["git", "show", f"{base}:{MANIFEST}"], cwd=repo).stdout
    new_text = run(["git", "show", f"{head}:{MANIFEST}"], cwd=repo).stdout
    return _only_schema_line(old_text, new_text, old, new)


def _exists(repo: Path, ref: str) -> bool:
    return run(
        ["git", "rev-parse", "--verify", "--quiet", ref], cwd=repo, check=False,
    ).returncode == 0


def switch(repo: Path) -> dict:
    require_git_root(repo)
    ensure_clean(repo)
    if not manifest_path(repo).is_file():
        raise MDFError("contract-switch 需要已接入 MDF 的仓库", code="not_initialized")
    trunk = trunk_branch(repo)
    if current_branch(repo) != trunk:
        raise MDFError(
            f"contract-switch 须在目标 trunk {trunk} 上执行", code="not_on_trunk",
        )
    text = manifest_path(repo).read_text(encoding="utf-8")
    declared = schema_in_text(text)
    if declared is None:
        raise MDFError(
            "manifest 必须恰好有一行 schema_version: <整数>", code="manifest.schema",
        )
    if declared > SCHEMA_VERSION:
        raise MDFError(
            f"本机契约 {SCHEMA_VERSION} 低于声明的 {declared}；更新命令：mdf upgrade",
            code="contract_tool_outdated",
        )
    if declared == SCHEMA_VERSION:
        return {"changed": False, "schema_version": SCHEMA_VERSION, "commit": None}
    updated = replace_schema_line(text, SCHEMA_VERSION)
    pr_mode = configured(repo).get("mode") == "pr"
    message = f"chore(mdf): 切换 MDF 契约到 {SCHEMA_VERSION}"
    result: dict = {"changed": True, "schema_version": SCHEMA_VERSION, "from": declared}
    if pr_mode:
        base = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        ref = f"refs/heads/{CONTRACT_BRANCH}"
        result.update(source=CONTRACT_BRANCH, target=trunk, base=base)
        if _exists(repo, ref):
            prepared = run(["git", "rev-parse", ref], cwd=repo).stdout.strip()
            if valid_contract_source(repo, base, prepared, trunk):
                return {**result, "commit": prepared, "changed": True}
            raise MDFError(
                f"{CONTRACT_BRANCH} 已存在；请先处理现有切换分支",
                code="contract_switch_branch_exists",
            )
        run(["git", "switch", "--no-track", "-c", CONTRACT_BRANCH], cwd=repo)
    manifest_path(repo).write_text(updated, encoding="utf-8")
    run(["git", "add", "--", MANIFEST], cwd=repo)
    run(["git", "commit", "--only", "-m", message, "--", MANIFEST], cwd=repo)
    result["commit"] = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    return result


def command_contract_switch(args) -> None:
    repo = repo_path(args.repo)
    from mdf_core.lifecycle.pull_finish import finish_lock
    with finish_lock(repo):
        emit({"ok": True, "operation": "contract-switch", **switch(repo)})
