"""`workflow` 命令：空闲态切换分支模型 / trunk，以及按配置渲染 CI 触发分支。"""

from __future__ import annotations

import json
from pathlib import Path

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.foundation.paths import load_manifest, manifest_path
from mdf_core.foundation.yamlutil import parse_yaml
from mdf_core.workspace.gitutil import (
    current_branch,
    ensure_clean,
    occupies_delivery,
    repo_path,
    require_git_root,
    run,
)
from mdf_core.workspace.workflow_policy import (
    GITFLOW,
    ci_branches,
    parse_workflow,
    render_workflow_lines,
    set_manifest_block,
    workflow_config,
)


def _git(repo: Path, *args: str, check: bool = True):
    return run(["git", *args], cwd=repo, check=check)


def _exists(repo: Path, ref: str) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0


def _in_flight_branches(repo: Path) -> list[str]:
    from mdf_core.workspace.workflow_policy import trunk_branch
    names = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").stdout.split()
    trunk = trunk_branch(repo)
    return sorted(name for name in names if occupies_delivery(name, trunk))


def _load_record(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _release_finished(folder: Path, version: str) -> bool:
    data = _load_record(folder / "release" / f"{version}.json")
    return bool(data and (data.get("completed") or data.get("pushed")))


def _pending_finish_records(repo: Path) -> list[str]:
    common = Path(_git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    folder = common / "mdf" / "finish"
    pending = []
    for path in sorted(folder.rglob("*.json")) if folder.is_dir() else []:
        rel = path.relative_to(folder).as_posix()
        if rel.startswith("sync/history/"):
            continue
        data = _load_record(path)
        if data is None:
            pending.append(rel)
            continue
        if rel.startswith("integrate/") and _release_finished(folder, path.stem):
            continue
        if not (data.get("completed") or data.get("pushed")):
            pending.append(rel)
    return pending


def _dirty_worktrees(repo: Path) -> list[str]:
    from mdf_core.workspace.gitutil import git_in_progress_head, git_is_clean, primary_worktree, worktree_map
    primary = primary_worktree(repo)
    dirty = []
    seen: set[Path] = set()
    for path in (*worktree_map(primary).values(), primary):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not git_is_clean(path) or git_in_progress_head(path) == "MERGE_HEAD":
            dirty.append(str(path))
    return dirty


def require_idle(repo: Path) -> None:
    """无在途交付分支、无未完成收口记录、关联 worktree 干净、无未落地 planning 提交。"""
    branches = _in_flight_branches(repo)
    if branches:
        raise MDFError("存在在途交付分支，不能切换 workflow", code="workflow_not_idle",
                       details={"branches": branches})
    records = _pending_finish_records(repo)
    if records:
        raise MDFError("存在未完成的收口记录，不能切换 workflow", code="workflow_not_idle",
                       details={"records": records})
    dirty = _dirty_worktrees(repo)
    if dirty:
        raise MDFError("关联 worktree 不干净或存在未完成的 merge，不能切换 workflow",
                       code="workflow_not_idle", details={"worktrees": dirty})
    planning = "refs/heads/planning"
    if (workflow_config(repo)["model"] == GITFLOW and _exists(repo, planning)
            and _git(repo, "merge-base", "--is-ancestor", planning, "HEAD", check=False).returncode):
        raise MDFError("planning 有未落地提交，不能切换 workflow", code="workflow_not_idle",
                       details={"branch": "planning"})


def switch(repo: Path, model: str | None, trunk: str | None) -> dict:
    """在目标 trunk 的干净 checkout 上改写 manifest 并提交；既有分支、历史与产出物不动。"""
    require_git_root(repo)
    ensure_clean(repo)
    if not manifest_path(repo).is_file():
        raise MDFError("workflow switch 需要已接入 MDF 的仓库", code="not_initialized")
    current = workflow_config(repo)
    wanted = parse_workflow({"workflow": {
        "model": model or current["model"], "trunk": trunk or current["trunk"],
    }}, repo)
    if current_branch(repo) != wanted["trunk"]:
        raise MDFError(f"workflow switch 须在目标 trunk {wanted['trunk']} 上执行", code="not_on_trunk")
    old = current["trunk"]
    if old != wanted["trunk"] and _exists(repo, f"refs/heads/{old}") and _git(
        repo, "merge-base", "--is-ancestor", f"refs/heads/{old}", "HEAD", check=False,
    ).returncode:
        raise MDFError(f"新 trunk 须包含原 trunk {old} 的历史", code="trunk_history_lost")
    if wanted == current and "workflow" in load_manifest(repo):
        return {"changed": False, "from": current, "to": wanted, "commit": None}
    require_idle(repo)
    if wanted["model"] == GITFLOW and not _exists(repo, "refs/heads/develop"):
        raise MDFError("切换到 gitflow 需要已有 develop 分支", code="missing_branch")
    path = manifest_path(repo)
    path.write_text(set_manifest_block(path.read_text(encoding="utf-8"), "workflow",
                                       render_workflow_lines(wanted)), encoding="utf-8")
    parse_workflow(parse_yaml(path.read_text(encoding="utf-8")), repo)
    _git(repo, "add", "--", ".mdf/manifest.yaml")
    _git(repo, "commit", "-m", f"chore(workflow): 切换到 {wanted['model']}（trunk {wanted['trunk']}）")
    return {"changed": True, "from": current, "to": wanted,
            "commit": _git(repo, "rev-parse", "HEAD").stdout.strip()}


_CI_TEMPLATES = {"github": "github-actions.yml", "gitlab": "gitlab-ci.yml"}


def render_ci(repo: Path, provider: str) -> str:
    """把模板中的 push 触发分支替换为当前 workflow 的分支集合。"""
    template = Path(__file__).resolve().parents[3] / "assets" / "ci" / _CI_TEMPLATES[provider]
    text = template.read_text(encoding="utf-8")
    branches = ci_branches(repo)
    if provider == "github":
        old = "    branches: [develop, master]"
        new = "    branches: [" + ", ".join(f"'{b}'" if "*" in b else b for b in branches) + "]"
    else:
        old = """($CI_COMMIT_BRANCH == "develop" || $CI_COMMIT_BRANCH == "master")"""
        clauses = [f'$CI_COMMIT_BRANCH == "{b}"' if "*" not in b else f'$CI_COMMIT_BRANCH =~ /^{b.replace("/", chr(92) + "/").replace("**", ".*")}$/'
                   for b in branches]
        new = "(" + " || ".join(clauses) + ")"
    if old not in text:
        raise MDFError("CI 模板的触发分支行已变化", code="invalid_ci_template")
    return text.replace(old, new, 1)


def command_workflow(args) -> None:
    repo = repo_path(args.repo)
    if args.action == "ci":
        require_git_root(repo)
        emit({"ok": True, "operation": "workflow-ci", "provider": args.provider,
              "branches": ci_branches(repo), "content": render_ci(repo, args.provider)})
        return
    if args.model is None and args.trunk is None:
        raise MDFError("workflow switch 需要 --model 或 --trunk", code="missing_argument")
    emit({"ok": True, "operation": "workflow-switch", **switch(repo, args.model, args.trunk)})
