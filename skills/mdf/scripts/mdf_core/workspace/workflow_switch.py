"""`workflow` 命令：空闲态切换分支模型 / trunk，以及按配置渲染 CI 触发分支。"""

from __future__ import annotations

from pathlib import Path
import subprocess

from mdf_core.foundation.errors import MDFError, emit
from mdf_core.foundation.paths import load_manifest, manifest_path
from mdf_core.foundation.yamlutil import parse_yaml
from mdf_core.workspace.agents_block import block_span, render_block
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
    GITHUB_FLOW,
    ci_branches,
    parse_workflow,
    render_workflow_lines,
    set_manifest_block,
    workflow_config,
)
from mdf_core.workspace.merge_policy import ancestor, config, paths


SWITCH_BRANCH = "codex/workflow-switch"
MANIFEST = ".mdf/manifest.yaml"


def _git(repo: Path, *args: str, check: bool = True):
    return run(["git", *args], cwd=repo, check=check)


def _exists(repo: Path, ref: str) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0


def _in_flight_branches(repo: Path, *, allow_switch: bool) -> list[str]:
    from mdf_core.workspace.workflow_policy import trunk_branch
    names = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").stdout.split()
    trunk = trunk_branch(repo)
    return sorted(name for name in names if occupies_delivery(name, trunk) and not (allow_switch and name == SWITCH_BRANCH))


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


def require_idle(repo: Path, *, allow_switch: bool) -> None:
    """核对交付分支、关联 worktree 与 planning 的 Git 现场。"""
    branches = _in_flight_branches(repo, allow_switch=allow_switch)
    if branches:
        raise MDFError("存在在途交付分支，不能切换 workflow", code="workflow_not_idle",
                       details={"branches": branches})
    if workflow_config(repo)["model"] == GITHUB_FLOW:
        from mdf_core.lifecycle.publish import pending_support_publications
        pending = pending_support_publications(repo)
        if pending:
            raise MDFError("存在待发布的 support hotfix，完成 publish 后再切换 workflow", code="workflow_not_idle",
                           details={"publications": pending})
    dirty = _dirty_worktrees(repo)
    if dirty:
        raise MDFError("关联 worktree 不干净或存在未完成的 merge，不能切换 workflow",
                       code="workflow_not_idle", details={"worktrees": dirty})
    planning = "refs/heads/planning"
    if (workflow_config(repo)["model"] == GITFLOW and _exists(repo, planning)
            and _git(repo, "merge-base", "--is-ancestor", planning, "HEAD", check=False).returncode):
        raise MDFError("planning 有未落地提交，不能切换 workflow", code="workflow_not_idle",
                       details={"branch": "planning"})


def _switch_files(manifest: bytes, agents: bytes | None, wanted: dict) -> dict[str, bytes]:
    text = manifest.decode("utf-8").replace("\r\n", "\n")
    text = set_manifest_block(text, "workflow", render_workflow_lines(wanted))
    files = {MANIFEST: text.encode("utf-8")}
    if agents is not None:
        text_agents = agents.decode("utf-8")
        if span := block_span(text_agents):
            start, end = span
            block = render_block(text_agents[start:end], parse_yaml(text))
            if block != text_agents[start:end]:
                files["AGENTS.md"] = (text_agents[:start] + block + text_agents[end:]).encode("utf-8")
    return files


def _blob(repo: Path, ref: str, path: str) -> tuple[str, bytes] | None:
    entry = _git(repo, "ls-tree", ref, "--", path).stdout.split()
    if not entry or entry[0] not in {"100644", "100755"}:
        return None
    return entry[0], subprocess.check_output(["git", "cat-file", "blob", entry[2]], cwd=repo)


def valid_switch_source(repo: Path, base: str, head: str, target: str) -> bool:
    """PR source 须从目标 tip 出发，且只包含 Core 渲染的配置更新。"""
    if _git(repo, "show", "-s", "--format=%P", head).stdout.split() != [base]:
        return False
    old_manifest = _blob(repo, base, MANIFEST)
    new_manifest = _blob(repo, head, MANIFEST)
    if not old_manifest or not new_manifest:
        return False
    old = parse_yaml(old_manifest[1].decode("utf-8"))
    wanted = parse_workflow(parse_yaml(new_manifest[1].decode("utf-8")), repo)
    if config(old)["mode"] != "pr" or wanted["trunk"] != target:
        return False
    if wanted == parse_workflow(old, repo) and "workflow" in old:
        return False
    agents = _blob(repo, base, "AGENTS.md")
    expected = _switch_files(old_manifest[1], agents[1] if agents else None, wanted)
    changed = paths(repo, base, head)
    if MANIFEST not in changed or set(changed) != set(expected):
        return False
    return all(_blob(repo, head, path) == (original[0], expected[path])
               for path, original in ((MANIFEST, old_manifest), ("AGENTS.md", agents)) if path in expected)


def _require_history(repo: Path, ref: str, branch: str, *, code: str) -> None:
    if not ancestor(repo, ref, "HEAD"):
        raise MDFError(f"目标 trunk 须包含 {branch} 的历史；请先合并 {branch}",
                       code=code, details={"branch": branch})


def _require_published_target(repo: Path, current: dict, wanted: dict, head: str) -> None:
    old, target = current["trunk"], wanted["trunk"]
    refs = [target, old]
    leaving_gitflow = current["model"] == GITFLOW and wanted["model"] == GITHUB_FLOW
    if leaving_gitflow:
        refs += ["develop", "planning"]
    remote = {ref.removeprefix("refs/heads/"): sha for sha, ref in (
        line.split() for line in _git(repo, "ls-remote", "--heads", "origin",
                                     *(f"refs/heads/{name}" for name in refs)).stdout.splitlines())}
    if remote.get(target) != head:
        raise MDFError(f"请先在 origin 建立并保护 {target}，再将本地目标 trunk 对齐到远端 tip",
                       code="workflow_target_not_synced", details={"branch": target})
    for branch, code in ((old, "trunk_history_lost"), ("develop", "develop_history_lost"),
                         ("planning", "workflow_not_idle")):
        if branch in remote:
            _require_history(repo, remote[branch], f"origin/{branch}", code=code)


def switch(repo: Path, model: str | None, trunk: str | None) -> dict:
    """从目标 trunk 切换配置；PR mode 在独立的 source 分支提交。"""
    require_git_root(repo)
    ensure_clean(repo)
    if not manifest_path(repo).is_file():
        raise MDFError("workflow switch 需要已接入 MDF 的仓库", code="not_initialized")
    manifest = load_manifest(repo)
    current = parse_workflow(manifest, repo)
    wanted = parse_workflow({"workflow": {
        "model": model or current["model"], "trunk": trunk or current["trunk"],
    }}, repo)
    if current_branch(repo) != wanted["trunk"]:
        raise MDFError(f"workflow switch 须在目标 trunk {wanted['trunk']} 上执行", code="not_on_trunk")
    old = current["trunk"]
    if old != wanted["trunk"] and _exists(repo, f"refs/heads/{old}"):
        _require_history(repo, f"refs/heads/{old}", old, code="trunk_history_lost")
    if wanted == current and "workflow" in manifest:
        return {"changed": False, "from": current, "to": wanted, "commit": None}
    pr_mode = config(manifest)["mode"] == "pr"
    require_idle(repo, allow_switch=pr_mode)
    develop = _exists(repo, "refs/heads/develop")
    if current["model"] == GITFLOW and wanted["model"] == GITHUB_FLOW and develop:
        _require_history(repo, "refs/heads/develop", "develop", code="develop_history_lost")
    if wanted["model"] == GITFLOW and not develop:
        raise MDFError("切换到 gitflow 需要已有 develop 分支", code="missing_branch")
    agents = repo / "AGENTS.md"
    files = _switch_files(manifest_path(repo).read_bytes(),
                          agents.read_bytes() if agents.is_file() and not agents.is_symlink() else None, wanted)
    result = {"changed": True, "from": current, "to": wanted}
    if pr_mode:
        base = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _require_published_target(repo, current, wanted, base)
        result.update(source=SWITCH_BRANCH, target=wanted["trunk"], base=base)
        ref = f"refs/heads/{SWITCH_BRANCH}"
        if _exists(repo, ref):
            prepared = _git(repo, "rev-parse", ref).stdout.strip()
            if valid_switch_source(repo, base, prepared, wanted["trunk"]) and workflow_config(repo, prepared) == wanted:
                return {**result, "commit": prepared}
            raise MDFError(f"{SWITCH_BRANCH} 已存在；请先处理现有切换分支", code="workflow_switch_branch_exists")
        _git(repo, "switch", "--no-track", "-c", SWITCH_BRANCH)
    for file, content in files.items():
        (repo / file).write_bytes(content)
    _git(repo, "add", "--", *files)
    _git(repo, "commit", "-m", f"chore(workflow): 切换到 {wanted['model']}（trunk {wanted['trunk']}）")
    return {**result, "commit": _git(repo, "rev-parse", "HEAD").stdout.strip()}


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
    from mdf_core.lifecycle.pull_finish import finish_lock
    with finish_lock(repo):
        emit({"ok": True, "operation": "workflow-switch", **switch(repo, args.model, args.trunk)})
